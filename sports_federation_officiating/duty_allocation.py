"""Pure allocation for draft club-duty previews."""

import hashlib
import json


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def allocate(rows, avoid_playing=True, allow_fallback=False):
    """Deterministic, side-effect-free allocation; one club supplies missing roles."""
    clubs = sorted({club for row in rows for club in row["opponents"]})
    load = {club: 0 for club in clubs}
    for row in rows:
        for club in row["existing_clubs"]:
            load[club] = load.get(club, 0) + 1
    result, issues = [], []
    for row in sorted(rows, key=lambda item: (item["start"], item["assignment"])):
        if not row["roles"]:
            continue
        if not row.get("resolved", len(row["opponents"]) == 2):
            issues.append(
                "Resolve both participating clubs for fixture %s." % row["fixture"]
            )
            continue
        playing = set().union(
            *(
                set(other["opponents"])
                for other in rows
                if row["start"] < other["end"] and other["start"] < row["end"]
            )
        )
        eligible = [club for club in clubs if club not in row["opponents"]]
        preferred = [club for club in eligible if club not in playing]
        pool = preferred if avoid_playing else eligible
        if not pool and allow_fallback:
            pool = eligible
        if not pool:
            issues.append("No eligible club for fixture %s." % row["fixture"])
            continue
        club = min(
            pool,
            key=lambda candidate: (
                candidate in playing,
                load.get(candidate, 0),
                candidate,
            ),
        )
        result.append(dict(row, club=club, fallback=club in playing))
        load[club] = load.get(club, 0) + len(row["roles"])
    return {
        "rows": result,
        "issues": issues,
        "load": {str(k): v for k, v in load.items()},
    }
