"""Pure planning arithmetic for the guided competition formats.

Nothing here touches the database, so the format wizard preview, the stage
graph engine and dependency-free CI checks all share one implementation of:

* how teams are spread over groups (snake seeding);
* which group places meet in the first knockout round (cross-seeding);
* how many playable matches a bracket or round robin produces;
* the match count and a readable outline of every guided format.
"""

from itertools import permutations
from math import ceil, log2

GUIDED_FORMATS = (
    "single_round_robin",
    "double_round_robin",
    "knockout",
    "pool_knockout",
    "split_pools",
)


def group_letter(index):
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def round_robin_count(teams, double=False):
    teams = max(0, int(teams or 0))
    matches = teams * (teams - 1) // 2
    return matches * 2 if double else matches


def round_robin_rounds(teams, double=False):
    teams = max(0, int(teams or 0))
    if teams < 2:
        return 0
    rounds = teams if teams % 2 else teams - 1
    return rounds * 2 if double else rounds


def round_robin_pairs(count, double=False):
    """Circle-method pairings of seeds 1..count, per round.

    Mirrors ``federation.fixture.generator.round.robin`` so a placeholder
    round robin plays exactly like one generated from known teams.
    """
    work = list(range(1, count + 1))
    if count % 2:
        work.append(None)
    rounds = []
    for round_index in range(len(work) - 1):
        pairs = []
        for index in range(len(work) // 2):
            first, second = work[index], work[-index - 1]
            if first and second:
                pairs.append(
                    (first, second) if round_index % 2 == 0 else (second, first)
                )
        rounds.append(pairs)
        work = [work[0], work[-1], *work[1:-1]]
    if double:
        rounds += [[(away, home) for home, away in pairs] for pairs in rounds]
    return rounds


def pool_sizes(teams, pool_count):
    pool_count = max(1, int(pool_count or 1))
    sizes = [teams // pool_count] * pool_count
    for index in range(teams % pool_count):
        sizes[index] += 1
    return sizes


def snake_pools(teams, pool_count):
    """Seed positions (0-based) per group, snake ordered: A B C C B A ..."""
    pool_count = max(1, int(pool_count or 1))
    pools = [[] for _index in range(pool_count)]
    for index in range(teams):
        round_index, pool_index = divmod(index, pool_count)
        if round_index % 2:
            pool_index = pool_count - 1 - pool_index
        pools[pool_index].append(index)
    return pools


def bracket_seed_order(size):
    order = [1, 2]
    while len(order) < size:
        mirror = len(order) * 2 + 1
        order = [x for seed in order for x in (seed, mirror - seed)]
    return order[:size] if size >= 2 else [1]


def bracket_size(count):
    return 2 ** ceil(log2(count)) if count > 1 else 1


def first_round_pairs(count):
    """Seed pairs that really play in round one (byes excluded)."""
    if count < 2:
        return []
    order = bracket_seed_order(bracket_size(count))
    return [
        (order[index], order[index + 1])
        for index in range(0, len(order), 2)
        if order[index] <= count and order[index + 1] <= count
    ]


def cross_seed(sizes, qualifiers_per_pool):
    """Knockout seeds for group places.

    Group winners take the best seeds, then the runners-up, and so on. Within
    every finishing place the group order is rotated so that, where the
    bracket allows it, two teams of the same group never meet in round one.

    Returns a list of ``(pool_index, rank, seed)`` sorted by seed.
    """
    qualifiers = max(1, int(qualifiers_per_pool or 1))
    tiers = []
    for rank in range(1, qualifiers + 1):
        tiers.append([index for index, size in enumerate(sizes) if size >= rank])
    total = sum(len(tier) for tier in tiers)
    pairs = first_round_pairs(total)
    placement = []
    next_seed = 1
    for rank, tier in enumerate(tiers, 1):
        best = None
        for rotated in _tier_orders(tier):
            candidate = placement + [
                (pool_index, rank, next_seed + offset)
                for offset, pool_index in enumerate(rotated)
            ]
            pool_by_seed = {seed: pool for pool, _rank, seed in candidate}
            clashes = sum(
                1
                for home, away in pairs
                if home in pool_by_seed
                and away in pool_by_seed
                and pool_by_seed[home] == pool_by_seed[away]
            )
            if best is None or clashes < best[0]:
                best = (clashes, candidate)
        placement = best[1]
        next_seed += len(tier)
    return sorted(placement, key=lambda item: item[2])


def _tier_orders(tier):
    """Group orders to try for one finishing place, most natural first."""
    orders = [tier[shift:] + tier[:shift] for shift in range(max(1, len(tier)))]
    if len(tier) <= 6:
        seen = {tuple(order) for order in orders}
        orders += [list(order) for order in permutations(tier) if order not in seen]
    return orders


def bracket_match_count(count, full_placement=False):
    """Playable matches of a (placement) bracket; byes are not counted.

    Mirrors the shape built by the stage graph engine: a single-elimination
    tree and, for full placement, recursive classification brackets fed by
    the losers of each round.
    """
    if count < 2:
        return 0
    order = bracket_seed_order(bracket_size(count))
    # Each node: number of real sides (0..2). A node "has a team" for its
    # winner when at least one side is real; it "has a loser" when both are.
    current = []
    for index in range(0, len(order), 2):
        real = int(order[index] <= count) + int(order[index + 1] <= count)
        current.append(real)
    played = sum(1 for real in current if real == 2)
    cohorts = []
    while len(current) > 1:
        cohorts.append(current)
        nxt = [2 for _index in range(0, len(current), 2)]
        played += len(nxt)
        current = nxt
    if full_placement:
        for cohort in reversed(cohorts):
            losers = sum(1 for real in cohort if real == 2)
            if losers > 1:
                played += _classification_count(losers)
    return played


def _classification_count(sources):
    if sources < 2:
        return 0
    if sources == 2:
        return 1
    matches = sources // 2
    winners = matches + sources % 2
    losers = matches
    return matches + _classification_count(winners) + _classification_count(losers)


def _invalid(message):
    return {
        "feasible": False,
        "fixture_count": 0,
        "message": message,
        "stages": [],
    }


def plan(
    format_type,
    teams,
    *,
    pool_count=2,
    qualifiers_per_pool=2,
    knockout_full_placement=False,
    split_rank=0,
    first_phase_double=False,
    second_phase_double=False,
):
    """Stage outline and match count of a guided format.

    ``stages`` is a list of dicts with ``name``, ``teams``, ``matches`` and
    ``source`` (a readable description of where its teams come from).
    """
    teams = int(teams or 0)
    if format_type not in GUIDED_FORMATS:
        return _invalid("Custom formats are counted after their stages are built.")
    if teams < 2:
        return _invalid("At least two teams are needed.")
    stages = []
    if format_type in ("single_round_robin", "double_round_robin"):
        double = format_type == "double_round_robin"
        stages.append(
            {
                "name": "League",
                "teams": teams,
                "matches": round_robin_count(teams, double),
                "source": "All teams",
            }
        )
    elif format_type == "knockout":
        stages.append(
            {
                "name": "Knockout",
                "teams": teams,
                "matches": bracket_match_count(teams, knockout_full_placement),
                "source": "All teams",
            }
        )
    elif format_type == "pool_knockout":
        pool_count = int(pool_count or 0)
        qualifiers = int(qualifiers_per_pool or 0)
        if pool_count < 1:
            return _invalid("Use at least one group.")
        if pool_count > teams // 2:
            return _invalid("Every group needs at least two teams.")
        if qualifiers < 1:
            return _invalid("At least one team per group must qualify.")
        sizes = pool_sizes(teams, pool_count)
        if qualifiers > min(sizes):
            return _invalid(
                "The smallest group has %s teams, so at most %s can qualify."
                % (min(sizes), min(sizes))
            )
        for index, size in enumerate(sizes):
            stages.append(
                {
                    "name": "Group %s" % group_letter(index),
                    "teams": size,
                    "matches": round_robin_count(size, first_phase_double),
                    "source": "Seeded teams",
                }
            )
        knockout_teams = qualifiers * pool_count
        if knockout_teams < 2:
            return _invalid("At least two teams must reach the knockout.")
        stages.append(
            {
                "name": "Knockout",
                "teams": knockout_teams,
                "matches": bracket_match_count(knockout_teams, knockout_full_placement),
                "source": "Top %s of every group" % qualifiers,
            }
        )
    elif format_type == "split_pools":
        top = int(split_rank or 0)
        if top < 2 or top > teams:
            return _invalid("The top group needs between 2 and %s teams." % teams)
        bottom = teams - top
        if bottom == 1:
            return _invalid("The bottom group would have one team. Move it to the top group.")
        stages.append(
            {
                "name": "Regular season",
                "teams": teams,
                "matches": round_robin_count(teams, first_phase_double),
                "source": "All teams",
            }
        )
        stages.append(
            {
                "name": "Second half" if not bottom else "Championship group",
                "teams": top,
                "matches": round_robin_count(top, second_phase_double),
                "source": "Places 1-%s" % top,
            }
        )
        if bottom:
            stages.append(
                {
                    "name": "Relegation group",
                    "teams": bottom,
                    "matches": round_robin_count(bottom, second_phase_double),
                    "source": "Places %s-%s" % (top + 1, teams),
                }
            )
    total = sum(stage["matches"] for stage in stages)
    return {
        "feasible": True,
        "fixture_count": total,
        "message": "%s matches for %s teams." % (total, teams),
        "stages": stages,
    }
