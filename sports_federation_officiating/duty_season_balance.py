"""Season-fair rebalancing of a reviewed club-duty allocation.

``duty_allocation.allocate`` assigns fixtures greedily and balances only the
schedule under review. This module moves those duties toward each club's season
duty-minute target. It is pure and deterministic, so the review preview, a
governed planning run and publication reproduce the same proposal, and CI can
test it without an Odoo registry.

Fairness never overrides a hard constraint:

* a club never officiates its own fixture;
* the club must be qualified for every role of the duty;
* weighted simultaneous roles, including preparation, rest and travel buffers,
  stay within the club's simultaneous capacity;
* pinned fixtures keep their club;
* when clubs playing at the same time are avoided without fallback, no duty
  moves to such a club.

Only clubs with a season target receive moved duties. A move or swap is kept
only when it lowers ``(fallback duties, squared deviation from target, changed
fixtures)`` lexicographically.
"""

from datetime import datetime, timedelta

try:  # Imported as part of the addon.
    from .duty_allocation import _policy
except ImportError:  # Imported standalone by the CI contract tests.
    from duty_allocation import _policy

MAX_ITERATIONS = 500


def _moment(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def role_minutes(row):
    """Duty minutes a row adds: its duration for every role it staffs."""
    duration = max(0, int(row.get("duration_minutes") or 0))
    return duration * len(row.get("roles") or ())


def peak_simultaneous(rows, buffer_minutes=0):
    """Return the highest number of roles staffed at the same moment.

    Each duty occupies ``[start, end + buffer)``, the interval used by the
    allocator's overlap test.
    """
    buffer = timedelta(minutes=max(0, int(buffer_minutes)))
    intervals = [
        (_moment(row["start"]), _moment(row["end"]) + buffer, len(row["roles"]))
        for row in rows
    ]
    peak = 0
    for start, _end, _weight in intervals:
        load = sum(
            weight for begin, finish, weight in intervals if begin <= start < finish
        )
        peak = max(peak, load)
    return peak


def playing_clubs(row, geometry):
    """Clubs playing a fixture that overlaps ``row`` in the reviewed schedule."""
    return {
        club
        for other in geometry
        if row["start"] < other["end"] and other["start"] < row["end"]
        for club in other["opponents"]
    }


def qualified(club, row, capacities):
    """True when ``club`` may staff every role of ``row``."""
    policy = _policy(capacities, club)
    return not policy["restricted"] or set(row["roles"]) <= policy["roles"]


def within_capacity(club, rows, capacities):
    """True when ``rows`` fit the club's simultaneous capacity and buffers."""
    policy = _policy(capacities, club)
    buffer = policy["preparation"] + policy["rest"] + policy["travel"]
    return peak_simultaneous(rows, buffer) <= policy["maximum"]


def rebalance_season(
    rows,
    geometry,
    capacities=None,
    avoid_playing=True,
    allow_fallback=False,
    season_minutes=None,
    targets=None,
    fixed_rows=None,
):
    """Return ``(rows, report)`` with duties moved toward season targets.

    ``rows`` are the rows returned by ``allocate``; their order is kept.
    ``geometry`` holds every fixture of the reviewed schedule and decides which
    clubs play concurrently. ``season_minutes`` and ``targets`` are keyed by club
    id, as an integer or a string. ``fixed_rows`` are preserved duties: they stay
    with their club, which is given by their ``club`` key, and occupy its
    simultaneous capacity.
    """
    targets = {
        str(club): int(minutes)
        for club, minutes in (targets or {}).items()
        if int(minutes) > 0
    }
    season = {
        str(club): int(minutes) for club, minutes in (season_minutes or {}).items()
    }
    rows = [dict(row) for row in rows]
    fixed = [dict(row) for row in (fixed_rows or ())]
    if not targets:
        return rows, {"engaged": False, "reason": "no_targets"}
    original = [row["club"] for row in rows]
    playing = [playing_clubs(row, geometry) for row in rows]
    clubs = sorted(
        {club for row in geometry for club in row["opponents"]}
        | {row["club"] for row in rows}
    )
    movable = [index for index, row in enumerate(rows) if not row.get("pinned")]

    def allowed(index, club):
        row = rows[index]
        if club in row["opponents"] or str(club) not in targets:
            return False
        if avoid_playing and not allow_fallback and club in playing[index]:
            return False
        return qualified(club, row, capacities)

    def feasible(club, state):
        mine = [rows[index] for index, owner in enumerate(state) if owner == club]
        mine += [row for row in fixed if row["club"] == club]
        return within_capacity(club, mine, capacities)

    def planned(state):
        totals = {}
        for index, club in enumerate(state):
            key = str(club)
            totals[key] = totals.get(key, 0) + role_minutes(rows[index])
        return totals

    def score(state):
        totals = planned(state)
        deviation = sum(
            (season.get(key, 0) + totals.get(key, 0) - target) ** 2
            for key, target in targets.items()
        )
        fallback = sum(
            1
            for index, club in enumerate(state)
            if avoid_playing and club in playing[index]
        )
        changed = sum(1 for index, club in enumerate(state) if club != original[index])
        return (fallback, deviation, changed)

    def candidates(state):
        for index in movable:
            for club in clubs:
                if club == state[index] or not allowed(index, club):
                    continue
                trial = list(state)
                trial[index] = club
                if feasible(club, trial):
                    yield trial
        for position, first in enumerate(movable):
            for second in movable[position + 1 :]:
                left, right = state[first], state[second]
                if left == right:
                    continue
                if not (allowed(first, right) and allowed(second, left)):
                    continue
                trial = list(state)
                trial[first], trial[second] = right, left
                if feasible(left, trial) and feasible(right, trial):
                    yield trial

    state = list(original)
    current = initial = score(state)
    for _iteration in range(MAX_ITERATIONS):
        best = None
        for trial in candidates(state):
            value = score(trial)
            if value < current and (best is None or value < best[0]):
                best = (value, trial)
        if best is None:
            break
        current, state = best

    result = [
        dict(
            row,
            club=state[index],
            fallback=state[index] in playing[index],
            rebalanced=state[index] != original[index],
            allocated_club=original[index],
        )
        for index, row in enumerate(rows)
    ]
    totals = planned(state)
    keys = sorted(set(targets) | set(totals), key=int)
    report = {
        "engaged": True,
        "targets": {key: targets.get(key, 0) for key in keys},
        "season_minutes": {key: season.get(key, 0) for key in keys},
        "planned_minutes": {key: totals.get(key, 0) for key in keys},
        "projected_minutes": {
            key: season.get(key, 0) + totals.get(key, 0) for key in keys
        },
        "deviation_minutes": {
            key: season.get(key, 0) + totals.get(key, 0) - targets[key]
            for key in keys
            if key in targets
        },
        "fallback_before": initial[0],
        "fallback_after": current[0],
        "objective_before": initial[1],
        "objective_after": current[1],
        "moved_fixtures": sorted(row["fixture"] for row in result if row["rebalanced"]),
    }
    return result, report
