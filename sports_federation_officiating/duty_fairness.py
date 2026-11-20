"""Season-fairness refinement for capacity-aware club-duty allocation.

Pure helpers (no Odoo import) so they are unit-testable without a runtime.
They refine an allocation produced by ``duty_allocation.allocate`` by moving
duties toward a quadratic season duty-minute target while respecting
simultaneous capacity, role qualification, opponents and manual pins.

The search minimises ``(capacity overload, squared deviation from target)``
lexicographically. An input allocation that already exceeds a club's
simultaneous capacity is therefore repaired first; fairness is only improved
once no move can reduce the overload. A move is accepted only when the
receiving club stays within its capacity.
"""

import random
from datetime import datetime


def _parse(value):
    if isinstance(value, datetime):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")


def _overlap(a, b):
    return _parse(a["start"]) < _parse(b["end"]) and _parse(b["start"]) < _parse(
        a["end"]
    )


def _club_duties(assignment, rows_by_fixture, club):
    return [rows_by_fixture[f] for f, owner in assignment.items() if owner == club]


def club_overload(assignment, rows_by_fixture, club, max_simultaneous):
    """Total excess of overlapping duties above ``max_simultaneous`` for a club.

    ``None`` means the club has no capacity policy and is unrestricted. Zero
    means the club is within capacity.
    """
    if max_simultaneous is None:
        return 0
    mine = _club_duties(assignment, rows_by_fixture, club)
    excess = 0
    for duty in mine:
        active = sum(1 for other in mine if _overlap(duty, other))
        excess += max(0, active - max_simultaneous)
    return excess


def concurrency_ok(assignment, rows_by_fixture, club, max_simultaneous):
    """True when *club* never exceeds *max_simultaneous* overlapping duties."""
    return club_overload(assignment, rows_by_fixture, club, max_simultaneous) == 0


def quadratic_objective(assignment, rows_by_fixture, season_minutes, targets):
    """Sum of squared deviation of (season + planned) minutes from target."""
    planned = dict(season_minutes)
    for fixture, club in assignment.items():
        planned[club] = (
            planned.get(club, 0) + rows_by_fixture[fixture]["duration_minutes"]
        )
    clubs = set(planned) | set(targets)
    return sum((planned.get(c, 0) - targets.get(c, 0)) ** 2 for c in clubs)


def _capacity(capacities, club):
    """Simultaneous capacity of ``club``; ``None`` when it has no policy."""
    policy = capacities.get(club)
    if policy is None:
        return None
    return max(0, int(policy.get("max_simultaneous", 1)))


def rebalance_quadratic(
    rows,
    capacities,
    pins=None,
    season_minutes=None,
    targets=None,
    iterations=4000,
    seed=0,
):
    """Local-search refinement minimising capacity overload, then
    quadratic season-fairness.

    ``rows`` are the *assigned* rows returned by ``allocate`` (each exposing
    ``fixture``, ``club``, ``start``, ``end``, ``duration_minutes``, ``roles``,
    ``opponents``). Returns ``(assignment, report)``. ``report["overload"]``
    is zero when every club is within its simultaneous capacity; it stays
    positive only when the instance has no capacity-feasible assignment that
    the search could reach.
    """
    rng = random.Random(seed)
    pins = pins or {}
    season_minutes = dict(season_minutes or {})
    targets = targets or {}
    rows_by_fixture = {row["fixture"]: row for row in rows}
    assignment = {row["fixture"]: row["club"] for row in rows}
    clubs = set(capacities) | set(assignment.values())

    def eligible(fixture):
        row = rows_by_fixture[fixture]
        need = set(row["roles"])
        options = []
        for club in sorted(capacities):
            if club in row["opponents"]:
                continue
            if need and not need.issubset(set(capacities[club].get("roles", []))):
                continue
            options.append(club)
        return options or [assignment[fixture]]

    def overload(state):
        return sum(
            club_overload(state, rows_by_fixture, club, _capacity(capacities, club))
            for club in clubs
        )

    def score(state):
        return (
            overload(state),
            quadratic_objective(state, rows_by_fixture, season_minutes, targets),
        )

    movable = [row["fixture"] for row in rows if row["fixture"] not in pins]
    current = score(assignment)
    if movable:
        for _ in range(iterations):
            fixture = rng.choice(movable)
            new_club = rng.choice(eligible(fixture))
            old_club = assignment[fixture]
            if new_club == old_club:
                continue
            assignment[fixture] = new_club
            receiving_ok = concurrency_ok(
                assignment, rows_by_fixture, new_club, _capacity(capacities, new_club)
            )
            if receiving_ok:
                trial = score(assignment)
                if trial < current:
                    current = trial
                    continue
            assignment[fixture] = old_club

    planned = dict(season_minutes)
    for fixture, club in assignment.items():
        planned[club] = (
            planned.get(club, 0) + rows_by_fixture[fixture]["duration_minutes"]
        )
    report = {
        "overload": current[0],
        "objective": current[1],
        "projected_minutes": planned,
        "max_deviation": max(
            (
                abs(planned.get(c, 0) - targets.get(c, 0))
                for c in set(planned) | set(targets)
            ),
            default=0,
        ),
    }
    return dict(assignment), report
