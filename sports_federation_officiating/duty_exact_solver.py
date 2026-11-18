"""Exact season-fair club-duty optimizer using OR-Tools CP-SAT.

OR-Tools is optional. When it is not installed, or the model cannot be solved,
``solve_season`` returns its input rows unchanged and says why, so the built-in
local search stays the result.

The model reassigns the duties of a feasible allocation under the same hard
constraints as ``duty_season_balance``: a club never officiates its own fixture,
must be qualified for every role, stays within its simultaneous capacity
including buffers and preserved duties, pinned fixtures keep their club, and
with strict playing-club avoidance no duty moves to a club playing at the same
time. Only clubs with a season target receive moved duties.

The objective is lexicographic: fallback duties, then squared deviation from
the season targets, then the number of fixtures changed from the allocator's
choice. One worker, a fixed seed and a deterministic time budget make the result
reproducible on any server, so preview, apply and publication agree.

The solver result replaces the hint only when it scores strictly better.
"""

from datetime import timedelta

try:  # Imported as part of the addon.
    from .duty_allocation import _policy
    from .duty_season_balance import _moment, playing_clubs, qualified, role_minutes
except ImportError:  # Imported standalone by the CI contract tests.
    from duty_allocation import _policy
    from duty_season_balance import _moment, playing_clubs, qualified, role_minutes

MAX_COEFFICIENT = 2**62


def exact_available():
    """True when OR-Tools CP-SAT can be imported on this server."""
    try:
        from ortools.sat.python import cp_model  # noqa: F401
    except Exception:  # pragma: no cover - depends on the environment
        return False
    return True


def _minutes(mapping):
    return {str(club): int(value) for club, value in (mapping or {}).items()}


def score_state(rows, state, playing, original, season, targets, avoid_playing):
    """Return ``((fallback, deviation, changed), planned_minutes)``."""
    totals = {}
    for index, club in enumerate(state):
        key = str(club)
        totals[key] = totals.get(key, 0) + role_minutes(rows[index])
    deviation = sum(
        (season.get(key, 0) + totals.get(key, 0) - target) ** 2
        for key, target in targets.items()
    )
    fallback = sum(
        1 for index, club in enumerate(state) if avoid_playing and club in playing[index]
    )
    changed = sum(1 for index, club in enumerate(state) if club != original[index])
    return (fallback, deviation, changed), totals


def _unchanged(rows, status, proven_optimal=False):
    return rows, {
        "engaged": False,
        "solver": "local_search",
        "solver_status": status,
        "proven_optimal": proven_optimal,
    }


def solve_season(
    rows,
    geometry,
    capacities=None,
    avoid_playing=True,
    allow_fallback=False,
    season_minutes=None,
    targets=None,
    fixed_rows=None,
    effort=5.0,
):
    """Return ``(rows, report)``; ``report["solver"]`` is ``exact`` when used."""
    targets = {key: value for key, value in _minutes(targets).items() if value > 0}
    season = _minutes(season_minutes)
    rows = [dict(row) for row in rows]
    fixed = [dict(row) for row in (fixed_rows or ())]
    if not targets or not rows:
        return _unchanged(rows, "nothing_to_optimize")
    try:
        from ortools.sat.python import cp_model
    except Exception:
        return _unchanged(rows, "exact_unavailable")

    count = len(rows)
    hint = [row["club"] for row in rows]
    original = [row.get("allocated_club", row["club"]) for row in rows]
    playing = [playing_clubs(row, geometry) for row in rows]
    clubs = sorted(
        {club for item in geometry for club in item["opponents"]}
        | set(hint)
        | set(original)
        | {row["club"] for row in fixed}
    )
    domains = []
    for index, row in enumerate(rows):
        options = {hint[index]}
        if not row.get("pinned"):
            options.add(original[index])
            for club in clubs:
                if club in row["opponents"] or str(club) not in targets:
                    continue
                if avoid_playing and not allow_fallback and club in playing[index]:
                    continue
                if qualified(club, row, capacities):
                    options.add(club)
        domains.append(sorted(options))

    model = cp_model.CpModel()
    choice = {}
    for index, options in enumerate(domains):
        literals = []
        for club in options:
            literal = model.NewBoolVar("duty_%d_club_%s" % (index, club))
            choice[index, club] = literal
            literals.append(literal)
            model.AddHint(literal, club == hint[index])
        model.AddExactlyOne(literals)

    for club in clubs:
        candidates = [index for index in range(count) if (index, club) in choice]
        if not candidates:
            continue
        policy = _policy(capacities, club)
        buffer = timedelta(
            minutes=policy["preparation"] + policy["rest"] + policy["travel"]
        )
        spans = [
            (
                _moment(rows[index]["start"]),
                _moment(rows[index]["end"]) + buffer,
                len(rows[index]["roles"]),
                index,
            )
            for index in candidates
        ]
        held = [
            (_moment(row["start"]), _moment(row["end"]) + buffer, len(row["roles"]))
            for row in fixed
            if row["club"] == club
        ]
        for point in sorted({span[0] for span in spans} | {span[0] for span in held}):
            terms = [
                weight * choice[index, club]
                for begin, finish, weight, index in spans
                if begin <= point < finish
            ]
            if terms:
                held_load = sum(
                    weight for begin, finish, weight in held if begin <= point < finish
                )
                model.Add(sum(terms) + held_load <= policy["maximum"])

    squares, square_bound = [], 0
    for key, target in sorted(targets.items(), key=lambda item: int(item[0])):
        club = int(key)
        reachable = [index for index in range(count) if (index, club) in choice]
        base = season.get(key, 0) - target
        high = base + sum(role_minutes(rows[index]) for index in reachable)
        deviation = model.NewIntVar(base, high, "deviation_%s" % key)
        model.Add(
            deviation
            == base
            + sum(role_minutes(rows[index]) * choice[index, club] for index in reachable)
        )
        bound = max(abs(base), abs(high))
        square = model.NewIntVar(0, bound * bound, "square_%s" % key)
        model.AddMultiplicationEquality(square, [deviation, deviation])
        squares.append(square)
        square_bound += bound * bound
    deviation_weight = count + 1
    fallback_weight = (square_bound + 1) * deviation_weight
    if fallback_weight * (count + 1) >= MAX_COEFFICIENT:
        return _unchanged(rows, "objective_too_large")
    fallback_terms = [
        literal
        for (index, club), literal in choice.items()
        if avoid_playing and club in playing[index]
    ]
    change_terms = [
        literal for (index, club), literal in choice.items() if club != original[index]
    ]
    model.Minimize(
        fallback_weight * sum(fallback_terms)
        + deviation_weight * sum(squares)
        + sum(change_terms)
    )

    solver = cp_model.CpSolver()
    parameters = solver.parameters
    parameters.max_deterministic_time = float(effort)
    parameters.random_seed = 0
    if hasattr(parameters, "num_workers"):
        parameters.num_workers = 1
    else:  # pragma: no cover - older OR-Tools
        parameters.num_search_workers = 1
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return _unchanged(rows, solver.StatusName(status).lower())
    proven = status == cp_model.OPTIMAL
    state = [
        next(club for club in domains[index] if solver.Value(choice[index, club]))
        for index in range(count)
    ]
    hint_score, _totals = score_state(
        rows, hint, playing, original, season, targets, avoid_playing
    )
    score, totals = score_state(
        rows, state, playing, original, season, targets, avoid_playing
    )
    if score >= hint_score:
        return _unchanged(rows, "no_improvement", proven_optimal=proven)

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
    keys = sorted(set(targets) | set(totals), key=int)
    return result, {
        "engaged": True,
        "solver": "exact",
        "solver_status": solver.StatusName(status).lower(),
        "proven_optimal": proven,
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
        "fallback_after": score[0],
        "objective_after": score[1],
        "moved_fixtures": sorted(row["fixture"] for row in result if row["rebalanced"]),
    }
