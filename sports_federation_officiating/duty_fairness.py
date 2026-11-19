"""Season-fairness refinement for capacity-aware club-duty allocation.

Pure helpers (no Odoo import) so they are unit-testable without a runtime.
They refine an allocation produced by ``duty_allocation.allocate`` by moving
duties toward a quadratic season duty-minute target, while preserving every
hard constraint the allocator already enforces: simultaneous capacity, role
qualification and manual pins.
"""

from datetime import datetime


def _parse(value):
    if isinstance(value, datetime):
        return value
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _overlap(a, b):
    return _parse(a["start"]) < _parse(b["end"]) and _parse(b["start"]) < _parse(
        a["end"]
    )


def concurrency_ok(assignment, rows_by_fixture, club, max_simultaneous):
    """True when *club* never exceeds *max_simultaneous* overlapping duties."""
    mine = [rows_by_fixture[f] for f, c in assignment.items() if c == club]
    for duty in mine:
        active = sum(1 for other in mine if _overlap(duty, other))
        if active > max_simultaneous:
            return False
    return True


def quadratic_objective(assignment, rows_by_fixture, season_minutes, targets):
    """Sum of squared deviation of (season + planned) minutes from target."""
    planned = dict(season_minutes)
    for fixture, club in assignment.items():
        planned[club] = (
            planned.get(club, 0) + rows_by_fixture[fixture]["duration_minutes"]
        )
    clubs = set(planned) | set(targets)
    return sum((planned.get(c, 0) - targets.get(c, 0)) ** 2 for c in clubs)


def rebalance_quadratic(
    rows,
    capacities,
    pins=None,
    season_minutes=None,
    targets=None,
    iterations=4000,
    seed=0,
):
    """Local-search refinement minimising quadratic season-fairness.

    ``rows`` are the *assigned* rows returned by ``allocate`` (each exposing
    ``fixture``, ``club``, ``start``, ``end``, ``duration_minutes``, ``roles``,
    ``opponents``). Returns ``(assignment, report)``.
    """
    import random as _r

    rng = _r.Random(seed)
    pins = pins or {}
    season_minutes = dict(season_minutes or {})
    rows_by_fixture = {row["fixture"]: row for row in rows}
    targets = targets or {}
    assignment = {row["fixture"]: row["club"] for row in rows}

    def eligible(fixture):
        row = rows_by_fixture[fixture]
        need = set(row["roles"])
        out = []
        for club, pol in capacities.items():
            if club in row["opponents"]:
                continue
            if need and not need.issubset(set(pol.get("roles", []))):
                continue
            out.append(club)
        return out or [assignment[fixture]]

    best = dict(assignment)
    best_score = quadratic_objective(best, rows_by_fixture, season_minutes, targets)
    for _ in range(iterations):
        fixture = rng.choice(rows)["fixture"]
        if fixture in pins:
            continue
        options = eligible(fixture)
        new_club = rng.choice(options)
        old = assignment[fixture]
        if new_club == old:
            continue
        assignment[fixture] = new_club
        cap = capacities.get(new_club, {}).get("max_simultaneous", 1)
        if concurrency_ok(assignment, rows_by_fixture, new_club, cap):
            score = quadratic_objective(
                assignment, rows_by_fixture, season_minutes, targets
            )
            if score < best_score:
                best_score, best = score, dict(assignment)
            else:
                assignment[fixture] = old
        else:
            assignment[fixture] = old

    planned = dict(season_minutes)
    for fixture, club in best.items():
        planned[club] = (
            planned.get(club, 0) + rows_by_fixture[fixture]["duration_minutes"]
        )
    report = {
        "objective": best_score,
        "projected_minutes": planned,
        "max_deviation": max(
            (
                abs(planned.get(c, 0) - targets.get(c, 0))
                for c in set(planned) | set(targets)
            ),
            default=0,
        ),
    }
    return best, report
