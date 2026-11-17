"""Pure allocation for draft club-duty previews."""

import hashlib
import json


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _policy(capacities, club):
    value = (capacities or {}).get(club) or (capacities or {}).get(str(club)) or {}
    roles = value.get("roles")
    return {
        "maximum": max(0, int(value.get("max_simultaneous", 999999))),
        "roles": set(roles or ()),
        "preparation": max(0, int(value.get("preparation_minutes", 0))),
        "rest": max(0, int(value.get("rest_minutes", 0))),
        "travel": max(0, int(value.get("travel_minutes", 0))),
    }


def _overlaps(left, right, buffer_minutes=0):
    """Compare ISO values without timezone-dependent conversion.

    Odoo serialises every schedule datetime in the same sortable UTC format.  The
    allocator deliberately remains importable without Odoo, so its CI contract
    tests can exercise capacity policy without starting a registry.
    """
    from datetime import datetime, timedelta

    def value(item):
        return datetime.fromisoformat(str(item).replace("Z", "+00:00"))

    buffer = timedelta(minutes=buffer_minutes)
    return (
        value(left["start"]) < value(right["end"]) + buffer
        and value(right["start"]) < value(left["end"]) + buffer
    )


def allocate(
    rows, avoid_playing=True, allow_fallback=False, capacities=None, pins=None
):
    """Allocate feasible duties with deterministic explanations.

    ``capacities`` is keyed by club id and describes simultaneous headcount,
    qualified roles and preparation/rest/travel buffers. ``pins`` is keyed by
    fixture id and is applied before the remaining rows are balanced.
    """
    clubs = sorted({club for row in rows for club in row["opponents"]})
    load = {club: 0 for club in clubs}
    minute_load = {club: 0 for club in clubs}
    assignments = {club: [] for club in clubs}
    for row in rows:
        for club in row["existing_clubs"]:
            load[club] = load.get(club, 0) + 1
    result, issues, details = [], [], []
    for row in sorted(rows, key=lambda item: (item["start"], item["assignment"])):
        if not row["roles"]:
            continue
        if not row.get("resolved", len(row["opponents"]) == 2):
            message = (
                "Resolve both participating clubs for fixture %s." % row["fixture"]
            )
            issues.append(message)
            details.append(
                {
                    "code": "participants_unresolved",
                    "fixture": row["fixture"],
                    "message": message,
                }
            )
            continue
        playing = set().union(
            *(
                set(other["opponents"])
                for other in rows
                if row["start"] < other["end"] and other["start"] < row["end"]
            )
        )
        rejected = {}
        eligible = []
        for club in clubs:
            if club in row["opponents"]:
                rejected[club] = "club is playing this fixture"
                continue
            policy = _policy(capacities, club)
            missing = (
                sorted(set(row["roles"]) - policy["roles"]) if policy["roles"] else []
            )
            if missing:
                rejected[club] = "missing qualifications for %s" % ", ".join(missing)
                continue
            overlapping = [
                other
                for other in assignments.get(club, [])
                if _overlaps(
                    row,
                    other,
                    policy["preparation"] + policy["rest"] + policy["travel"],
                )
            ]
            simultaneous = sum(len(other["roles"]) for other in overlapping) + len(
                row["roles"]
            )
            if simultaneous > policy["maximum"]:
                rejected[club] = (
                    "simultaneous capacity %s would be exceeded" % policy["maximum"]
                )
                continue
            eligible.append(club)
        preferred = [club for club in eligible if club not in playing]
        pinned = (pins or {}).get(row["fixture"]) or (pins or {}).get(
            str(row["fixture"])
        )
        if pinned:
            pool = [int(pinned)] if int(pinned) in eligible else []
            if not pool:
                message = "Pinned club %s is not feasible for fixture %s: %s." % (
                    pinned,
                    row["fixture"],
                    rejected.get(int(pinned), "not eligible"),
                )
                issues.append(message)
                details.append(
                    {
                        "code": "pin_conflict",
                        "fixture": row["fixture"],
                        "club": int(pinned),
                        "message": message,
                        "rejected": rejected,
                    }
                )
                continue
        else:
            pool = preferred if avoid_playing else eligible
        if not pool and allow_fallback:
            pool = eligible
        if not pool:
            message = "No feasible club for fixture %s." % row["fixture"]
            issues.append(message)
            details.append(
                {
                    "code": "capacity_conflict",
                    "fixture": row["fixture"],
                    "message": message,
                    "rejected": rejected,
                }
            )
            continue
        club = min(
            pool,
            key=lambda candidate: (
                candidate in playing,
                load.get(candidate, 0),
                candidate,
            ),
        )
        duration = max(0, int(row.get("duration_minutes", 0)))
        allocated = dict(row, club=club, fallback=club in playing, pinned=bool(pinned))
        result.append(allocated)
        assignments.setdefault(club, []).append(allocated)
        load[club] = load.get(club, 0) + len(row["roles"])
        minute_load[club] = minute_load.get(club, 0) + duration * len(row["roles"])
    return {
        "rows": result,
        "issues": issues,
        "issue_details": details,
        "load": {str(k): v for k, v in load.items()},
        "minute_load": {str(k): v for k, v in minute_load.items()},
    }
