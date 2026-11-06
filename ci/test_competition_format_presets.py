"""Dependency-free checks for guided formats and stage-aware distribution.

Covers the pure format arithmetic shared by the format wizard and the stage
graph engine, and runs the competition distributor against small stand-in
records. It does not replace the Odoo integration tests tagged
``sf_competition_formats``.
"""

import importlib.util
import sys
import types
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


presets = _load(
    "format_presets", "sports_federation_format/services/format_presets.py"
)


def _load_distributor():
    odoo = types.ModuleType("odoo")
    odoo.models = types.SimpleNamespace(AbstractModel=object)
    previous = sys.modules.get("odoo")
    sys.modules["odoo"] = odoo
    try:
        return _load(
            "competition_distributor",
            "sports_federation_scheduling/services/competition_distributor.py",
        )
    finally:
        if previous is None:
            del sys.modules["odoo"]
        else:
            sys.modules["odoo"] = previous


class Records(list):
    """Just enough of a recordset for the distributor."""

    @property
    def ids(self):
        return [record.id for record in self]

    def filtered(self, predicate):
        return Records(record for record in self if predicate(record))

    def browse(self, record_id):
        return Records(record for record in self if record.id == record_id)

    def exists(self):
        return self[0] if self else None

    def mapped(self, name):
        return Records(getattr(record, name) for record in self)

    def _planning_sorted(self):
        return Records(
            sorted(
                self,
                key=lambda f: (f.stage_id.depth, f.round_number, f.sequence, f.stage_id.sequence, f.id),
            )
        )


class Stage:
    _fields = {"matchday_ids": True}

    def __init__(self, stage_id, name, depth=0, sources=(), days=()):
        self.id = stage_id
        self.name = self.display_name = name
        self.depth = depth
        self.sequence = stage_id
        self._sources = Records(sources)
        self.matchday_ids = Records(types.SimpleNamespace(id=day) for day in days)

    def _planning_source_stages(self):
        return self._sources


class Fixture:
    def __init__(self, fixture_id, stage, round_number, keys, home_source=None):
        self.id = fixture_id
        self.stage_id = stage
        self.round_number = round_number
        self.sequence = fixture_id
        self.division_id = types.SimpleNamespace(id=1, display_name="Division")
        self.display_name = "F%s" % fixture_id
        self.home_source_fixture_id = home_source
        self.away_source_fixture_id = None
        self._keys = set(keys)

    def _planning_keys(self):
        return self._keys


class FormatPresetTests(unittest.TestCase):
    def test_round_robin_pairs_every_opponent_once(self):
        for teams in range(2, 11):
            pairs = [pair for rnd in presets.round_robin_pairs(teams) for pair in rnd]
            self.assertEqual(len(pairs), presets.round_robin_count(teams))
            self.assertEqual(len({frozenset(pair) for pair in pairs}), len(pairs))
            double = [p for rnd in presets.round_robin_pairs(teams, True) for p in rnd]
            self.assertEqual(len(set(double)), presets.round_robin_count(teams, True))

    def test_cross_seeding_avoids_same_group_in_round_one(self):
        for pools in range(2, 7):
            for qualifiers in (1, 2, 3):
                sizes = [4] * pools
                placement = presets.cross_seed(sizes, qualifiers)
                self.assertEqual(
                    [seed for _pool, _rank, seed in placement],
                    list(range(1, pools * qualifiers + 1)),
                )
                group = {seed: pool for pool, _rank, seed in placement}
                if pools * qualifiers < 2:
                    continue
                clashes = [
                    pair
                    for pair in presets.first_round_pairs(pools * qualifiers)
                    if group[pair[0]] == group[pair[1]]
                ]
                self.assertFalse(clashes, (pools, qualifiers, placement))

    def test_group_winners_get_the_best_seeds(self):
        placement = presets.cross_seed([4, 4, 4, 4], 2)
        self.assertEqual({rank for _pool, rank, seed in placement if seed <= 4}, {1})

    def test_bracket_counts(self):
        for teams in range(2, 33):
            self.assertEqual(presets.bracket_match_count(teams), teams - 1)
        self.assertEqual(presets.bracket_match_count(4, True), 4)
        self.assertEqual(presets.bracket_match_count(8, True), 12)
        self.assertEqual(presets.bracket_match_count(16, True), 32)

    def test_guided_plans(self):
        groups = presets.plan("pool_knockout", 8, pool_count=2, qualifiers_per_pool=2)
        self.assertEqual(groups["fixture_count"], 6 + 6 + 3)
        self.assertEqual([s["name"] for s in groups["stages"]], ["Group A", "Group B", "Knockout"])
        three = presets.plan("pool_knockout", 12, pool_count=3, qualifiers_per_pool=3)
        self.assertEqual(three["stages"][-1]["teams"], 9)
        split = presets.plan("split_pools", 10, split_rank=6)
        self.assertEqual(split["fixture_count"], 45 + 15 + 6)
        halves = presets.plan("split_pools", 8, split_rank=8)
        self.assertEqual([s["name"] for s in halves["stages"]], ["Regular season", "Second half"])
        self.assertFalse(presets.plan("split_pools", 8, split_rank=7)["feasible"])
        self.assertFalse(presets.plan("pool_knockout", 8, pool_count=2, qualifiers_per_pool=5)["feasible"])
        self.assertFalse(presets.plan("custom", 8)["feasible"])


class DistributorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.Distributor = _load_distributor().FederationCompetitionScheduleDistributor

    def _days(self, *dates):
        return [
            {"matchday_id": index, "date": value, "capacity": 20, "division_ids": []}
            for index, value in enumerate(dates, 1)
        ]

    def _day_of(self, result, fixture):
        return next(day for day, ids in result["assignments"].items() if fixture.id in ids)

    def test_split_season_starts_after_the_regular_season(self):
        season = Stage(1, "Regular season")
        top = Stage(2, "Championship group", depth=1, sources=[season])
        fixtures = Records(
            [Fixture(i, season, i, {i, i + 100}) for i in range(1, 5)]
            + [Fixture(10, top, 1, {("seed", 2, 1), ("seed", 2, 2)})]
        )
        days = self._days(date(2027, 1, 1), date(2027, 1, 8), date(2027, 1, 15))
        result = self.Distributor().propose(fixtures, days)
        self.assertFalse(result["errors"])
        season_days = {self._day_of(result, f) for f in fixtures[:4]}
        self.assertGreater(len(season_days), 1)
        self.assertGreater(self._day_of(result, fixtures[4]), max(season_days))

    def test_tournament_day_may_continue_on_the_same_day(self):
        groups = Stage(1, "Group A")
        knockout = Stage(2, "Knockout", depth=1, sources=[groups])
        fixtures = Records(
            [Fixture(1, groups, 1, {1, 2}), Fixture(2, knockout, 1, {("seed", 2, 1)})]
        )
        result = self.Distributor().propose(fixtures, self._days(date(2027, 3, 6)))
        self.assertFalse(result["errors"])
        self.assertEqual(self._day_of(result, fixtures[1]), 1)

    def test_stage_game_days_are_respected_and_explained(self):
        season = Stage(1, "Regular season", days=[1])
        top = Stage(2, "Second half", depth=1, sources=[season], days=[3])
        fixtures = Records([Fixture(1, season, 1, {1, 2}), Fixture(2, top, 1, {("s", 1)})])
        result = self.Distributor().propose(
            fixtures, self._days(date(2027, 1, 1), date(2027, 1, 8), date(2027, 1, 15))
        )
        self.assertEqual(self._day_of(result, fixtures[0]), 1)
        self.assertEqual(self._day_of(result, fixtures[1]), 3)
        blocked = Stage(3, "Finals", depth=1, sources=[season], days=[1])
        season_two = Stage(4, "Season", days=[2])
        blocked._sources = Records([season_two])
        late = Records([Fixture(5, season_two, 1, {1, 2}), Fixture(6, blocked, 1, {("s", 3)})])
        result = self.Distributor().propose(
            late, self._days(date(2027, 1, 1), date(2027, 1, 8))
        )
        self.assertTrue(any("Finals" in error for error in result["errors"]))

    def test_follow_up_match_not_before_its_source(self):
        knockout = Stage(1, "Knockout")
        semi = Fixture(1, knockout, 1, {1, 2})
        final = Fixture(2, knockout, 2, {("fixture", 1, "winner")}, home_source=semi)
        result = self.Distributor().propose(
            Records([semi, final]),
            self._days(date(2027, 1, 1), date(2027, 1, 8)),
            known_days={},
        )
        self.assertGreaterEqual(self._day_of(result, final), self._day_of(result, semi))


    def test_season_groups_then_knockout_rounds_on_their_own_days(self):
        groups = Stage(1, "Group A")
        knockout = Stage(2, "Knockout", depth=1, sources=[groups])
        group_matches = [Fixture(i, groups, i, {i, i + 50}) for i in range(1, 7)]
        semi_one = Fixture(20, knockout, 1, {("seed", 2, 1), ("seed", 2, 4)})
        semi_two = Fixture(21, knockout, 1, {("seed", 2, 2), ("seed", 2, 3)})
        final = Fixture(22, knockout, 2, {("fixture", 20, "winner")}, home_source=semi_one)
        fixtures = Records(group_matches + [semi_one, semi_two, final])
        days = self._days(*[date(2027, 1, day) for day in (1, 8, 15, 22, 29)])
        result = self.Distributor().propose(fixtures, days)
        self.assertFalse(result["errors"])
        last_group_day = max(self._day_of(result, f) for f in group_matches)
        self.assertLessEqual(last_group_day, 3)
        self.assertEqual(self._day_of(result, semi_one), self._day_of(result, semi_two))
        self.assertGreater(self._day_of(result, semi_one), last_group_day)
        self.assertGreater(self._day_of(result, final), self._day_of(result, semi_one))


    def _league(self, teams, double=True):
        stage = Stage(1, "League")
        fixtures, number = [], 0
        for round_number, pairs in enumerate(presets.round_robin_pairs(teams, double), 1):
            for home, away in pairs:
                number += 1
                fixtures.append(Fixture(number, stage, round_number, {home, away}))
        return Records(fixtures)

    def _loads(self, result, fixtures):
        by_id = {fixture.id: fixture for fixture in fixtures}
        loads = {}
        for day, ids in result["assignments"].items():
            for fixture_id in ids:
                for key in by_id[fixture_id]._keys:
                    loads.setdefault((day, key), 0)
                    loads[(day, key)] += 1
        return loads

    def test_team_matches_are_spread_within_the_rest_limit(self):
        # 9 teams home & away: 16 matches per team over 3 tournament days,
        # 7 per team per day with the rest. Spread evenly: at most 6 per day.
        fixtures = self._league(9)
        days = [
            {"matchday_id": index, "date": date(2027, 1, index * 7), "capacity": 40,
             "division_ids": [], "team_limit": 7}
            for index in (1, 2, 3)
        ]
        result = self.Distributor().propose(fixtures, days)
        self.assertFalse(result["errors"])
        loads = self._loads(result, fixtures)
        self.assertLessEqual(max(loads.values()), 6)

    def test_rest_limit_is_respected_when_capacity_is_uneven(self):
        # A huge first day used to attract most matches; the rest limit now
        # sends the overflow to the other days.
        fixtures = self._league(6)
        days = [
            {"matchday_id": 1, "date": date(2027, 1, 7), "capacity": 60, "division_ids": [], "team_limit": 4},
            {"matchday_id": 2, "date": date(2027, 1, 14), "capacity": 10, "division_ids": [], "team_limit": 4},
            {"matchday_id": 3, "date": date(2027, 1, 21), "capacity": 10, "division_ids": [], "team_limit": 4},
        ]
        result = self.Distributor().propose(fixtures, days)
        self.assertFalse(result["errors"])
        self.assertLessEqual(max(self._loads(result, fixtures).values()), 4)

    def test_two_tournament_days_fit_exactly(self):
        # 8 teams home & away: 14 matches each, exactly 7 + 7 with the rest.
        fixtures = self._league(8)
        days = [
            {"matchday_id": index, "date": date(2027, 1, index * 7), "capacity": 60,
             "division_ids": [], "team_limit": 7}
            for index in (1, 2)
        ]
        result = self.Distributor().propose(fixtures, days)
        self.assertFalse(result["errors"])
        self.assertEqual(max(self._loads(result, fixtures).values()), 7)

    def test_more_matches_than_rest_allows_still_plans_everything(self):
        fixtures = self._league(9)
        days = [
            {"matchday_id": index, "date": date(2027, 1, index * 7), "capacity": 40,
             "division_ids": [], "team_limit": 7}
            for index in (1, 2)
        ]
        result = self.Distributor().propose(fixtures, days)
        self.assertFalse(result["errors"])
        self.assertEqual(sum(len(ids) for ids in result["assignments"].values()), len(fixtures))
        # 16 matches over two days of at most 7 cannot fit: everything is still
        # planned and the planner reports the shortfall with the numbers.
        self.assertLessEqual(max(self._loads(result, fixtures).values()), 9)


if __name__ == "__main__":
    unittest.main()
