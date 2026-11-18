#!/usr/bin/env python3
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "duty_fairness", ROOT / "sports_federation_officiating" / "duty_fairness.py"
)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def row(fixture, club, start, end, roles, opponents, minutes=60):
    return {"fixture": fixture, "club": club, "start": start, "end": end,
            "duration_minutes": minutes, "roles": roles, "opponents": opponents}


class DutyFairnessTest(unittest.TestCase):
    def _caps(self, ids, roles=("table",), mx=2):
        return {i: {"max_simultaneous": mx, "roles": list(roles)} for i in ids}

    def test_quadratic_rebalance_reduces_deviation(self):
        rows = [row(i, 1, "2026-11-17 10:00:00", "2026-11-17 11:00:00", ["table"], [9, 8])
                for i in range(6)]
        caps = self._caps([1, 2, 3])
        targets = {1: 120, 2: 120, 3: 120}
        base = M.quadratic_objective({r["fixture"]: 1 for r in rows},
                                     {r["fixture"]: r for r in rows}, {}, targets)
        _, report = M.rebalance_quadratic(rows, caps, targets=targets, seed=1)
        self.assertLess(report["objective"], base)

    def test_simultaneous_capacity_is_respected(self):
        rows = [row(i, 1, "2026-11-17 10:00:00", "2026-11-17 11:00:00", ["table"], [9, 8])
                for i in range(4)]
        caps = self._caps([1, 2, 3, 4], mx=1)
        assign, _ = M.rebalance_quadratic(rows, caps, targets={1: 60, 2: 60, 3: 60, 4: 60}, seed=2)
        by = {r["fixture"]: r for r in rows}
        for club in set(assign.values()):
            self.assertTrue(M.concurrency_ok(assign, by, club, 1))

    def test_pins_are_preserved(self):
        rows = [row(0, 1, "2026-11-17 10:00:00", "2026-11-17 11:00:00", ["table"], [9, 8]),
                row(1, 2, "2026-11-17 12:00:00", "2026-11-17 13:00:00", ["table"], [9, 8])]
        assign, _ = M.rebalance_quadratic(rows, self._caps([1, 2, 3]),
                                          pins={0: 1}, targets={1: 0, 2: 120, 3: 120}, seed=3)
        self.assertEqual(assign[0], 1)

    def test_season_ledger_biases_future_allocation(self):
        rows = [row(0, 1, "2026-11-17 10:00:00", "2026-11-17 11:00:00", ["table"], [9, 8])]
        # club 1 already heavily loaded this season -> should move to club 2
        assign, _ = M.rebalance_quadratic(rows, self._caps([1, 2]),
                                          season_minutes={1: 600, 2: 0},
                                          targets={1: 300, 2: 300}, seed=4)
        self.assertEqual(assign[0], 2)


if __name__ == "__main__":
    unittest.main()
