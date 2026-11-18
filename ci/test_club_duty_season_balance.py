#!/usr/bin/env python3
"""Contract tests for season-fair club-duty rebalancing; no Odoo needed."""

import json
import pathlib
import sys
import unittest

ADDON = pathlib.Path(__file__).resolve().parents[1] / "sports_federation_officiating"
sys.path.insert(0, str(ADDON))

import duty_allocation  # noqa: E402
import duty_season_balance as balance  # noqa: E402

T10 = ("2026-11-21 10:00:00", "2026-11-21 11:00:00")
T12 = ("2026-11-21 12:00:00", "2026-11-21 13:00:00")
T14 = ("2026-11-21 14:00:00", "2026-11-21 15:00:00")
TARGETS = {1: 300, 2: 300}
SEASON = {1: 600}


def fixture(number, slot, opponents, roles=("table",)):
    return {
        "assignment": number,
        "fixture": number,
        "start": slot[0],
        "end": slot[1],
        "duration_minutes": 60,
        "roles": list(roles),
        "opponents": list(opponents),
        "resolved": True,
        "existing_clubs": [],
    }


def duty(number, club, slot, opponents, pinned=False):
    return dict(
        fixture(number, slot, opponents), club=club, fallback=False, pinned=pinned
    )


CLUBS_ONE_AND_TWO = fixture(1, T10, (1, 2), roles=())


def run(rows, extra=(CLUBS_ONE_AND_TWO,), **options):
    options.setdefault("season_minutes", SEASON)
    options.setdefault("targets", TARGETS)
    geometry = [dict(row) for row in rows] + [dict(item) for item in extra]
    return balance.rebalance_season(rows, geometry, **options)


def clubs(rows):
    return [row["club"] for row in rows]


class SeasonBalanceTest(unittest.TestCase):
    def setUp(self):
        self.rows = [duty(2, 1, T12, (3, 4)), duty(3, 1, T14, (5, 6))]

    def test_over_target_club_sheds_duties(self):
        rows, report = run(self.rows)
        self.assertEqual(clubs(rows), [2, 2])
        self.assertEqual(report["projected_minutes"], {"1": 600, "2": 120})
        self.assertEqual(report["deviation_minutes"], {"1": 300, "2": -180})
        self.assertLess(report["objective_after"], report["objective_before"])
        self.assertEqual(report["moved_fixtures"], [2, 3])

    def test_pinned_fixture_keeps_its_club(self):
        self.rows[0]["pinned"] = True
        rows, _report = run(self.rows)
        self.assertEqual(clubs(rows), [1, 2])

    def test_opponents_are_never_selected(self):
        rows, _report = run(self.rows, targets={club: 300 for club in range(1, 8)})
        for row in rows:
            self.assertNotIn(row["club"], row["opponents"])

    def test_qualified_roles_are_respected(self):
        heads_only = {2: {"max_simultaneous": 2, "roles": ["head"]}}
        rows, report = run(self.rows, capacities=heads_only)
        self.assertEqual(clubs(rows), [1, 1])
        self.assertEqual(report["moved_fixtures"], [])

    def test_strict_playing_policy_blocks_concurrent_clubs(self):
        extra = (CLUBS_ONE_AND_TWO, fixture(9, T12, (2, 7), roles=()))
        for allow_fallback in (False, True):
            rows, report = run(self.rows, extra=extra, allow_fallback=allow_fallback)
            self.assertEqual(clubs(rows), [1, 2])
            self.assertEqual(report["fallback_after"], 0)

    def test_buffers_limit_simultaneous_capacity(self):
        tight = {2: {"max_simultaneous": 1, "roles": ["table"], "rest_minutes": 90}}
        rows, _report = run(self.rows, capacities=tight)
        self.assertEqual(clubs(rows).count(2), 1)
        loose = {2: {"max_simultaneous": 1, "roles": ["table"]}}
        rows, _report = run(self.rows, capacities=loose)
        self.assertEqual(clubs(rows), [2, 2])

    def test_clubs_without_target_receive_nothing(self):
        rows, _report = run(self.rows, targets={1: 300})
        self.assertEqual(clubs(rows), [1, 1])

    def test_without_targets_nothing_changes(self):
        rows, report = run(self.rows, targets={})
        self.assertEqual(clubs(rows), [1, 1])
        self.assertFalse(report["engaged"])

    def test_result_is_deterministic_and_json_stable(self):
        first, second = run(self.rows), run(self.rows)
        self.assertEqual(first, second)
        self.assertEqual(json.loads(json.dumps(first[0])), first[0])
        self.assertEqual(json.loads(json.dumps(first[1])), first[1])

    def test_peak_counts_buffers(self):
        self.assertEqual(balance.peak_simultaneous(self.rows), 1)
        self.assertEqual(balance.peak_simultaneous(self.rows, 90), 2)


class AllocationIntegrationTest(unittest.TestCase):
    def test_allocation_then_balance_stays_feasible(self):
        geometry = [
            fixture(1, T10, (1, 2)),
            fixture(2, T12, (3, 4)),
            fixture(3, T14, (5, 6)),
        ]
        allocation = duty_allocation.allocate(geometry, avoid_playing=True)
        self.assertEqual(clubs(allocation["rows"]), [3, 1, 2])
        rows, _report = balance.rebalance_season(
            allocation["rows"], geometry, season_minutes={}, targets={4: 180}
        )
        self.assertEqual(clubs(rows), [4, 1, 4])
        for row in rows:
            self.assertNotIn(row["club"], row["opponents"])

    def test_policy_without_qualified_roles_qualifies_nothing(self):
        rows = [fixture(1, T10, (1, 2)), fixture(2, T12, (3, 4), roles=())]
        policies = {
            3: {"max_simultaneous": 2, "roles": []},
            4: {"max_simultaneous": 2, "roles": ["table"]},
        }
        allocation = duty_allocation.allocate(
            rows, avoid_playing=False, capacities=policies
        )
        self.assertEqual(clubs(allocation["rows"]), [4])


if __name__ == "__main__":
    unittest.main()
