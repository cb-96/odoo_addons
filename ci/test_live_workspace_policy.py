import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("live_policy", Path(__file__).resolve().parents[1] /
    "sports_federation_live_workspace/policy.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class TestCapturePolicy(unittest.TestCase):
    def payload(self, **values):
        return {"home": 2, "away": 1, **values}

    def test_aggregate(self):
        self.assertEqual(p.validate_capture(self.payload())["home"], 2)

    def test_negative(self):
        with self.assertRaises(ValueError): p.validate_capture(self.payload(home=-1))

    def test_bool_score(self):
        with self.assertRaises(ValueError): p.validate_capture(self.payload(home=True))

    def test_fraction(self):
        with self.assertRaises(ValueError): p.validate_capture(self.payload(home=1.2))

    def test_large_score(self):
        with self.assertRaises(ValueError): p.validate_capture(self.payload(home=100001))

    def test_unknown_field(self):
        with self.assertRaises(ValueError): p.validate_capture(self.payload(approved=True))

    def test_period_sum(self):
        self.assertEqual(p.validate_capture(self.payload(periods=[{"home": 2, "away": 1}]), "periods")["home"], 2)

    def test_period_mismatch(self):
        with self.assertRaises(ValueError): p.validate_capture(self.payload(periods=[{"home": 3, "away": 1}]), "periods")

    def test_empty_period_submission(self):
        with self.assertRaises(ValueError): p.validate_capture(self.payload(), "periods")

    def test_empty_period_draft(self):
        p.validate_capture(self.payload(), "periods", complete=False)

    def test_set_wins(self):
        p.validate_capture(self.payload(periods=[{"home": 6, "away": 2}, {"home": 2, "away": 6},
                                               {"home": 6, "away": 3}]), "sets", set_target=2)

    def test_tied_set(self):
        with self.assertRaises(ValueError): p.validate_capture(self.payload(periods=[{"home": 2, "away": 2}]), "sets")

    def test_extra_set_after_target(self):
        with self.assertRaises(ValueError): p.validate_capture(self.payload(home=3, away=0,
            periods=[{"home": 6, "away": 2}] * 3), "sets", set_target=2)

    def test_exception_reason(self):
        with self.assertRaises(ValueError): p.validate_capture(self.payload(outcome="abandoned"))

    def test_interruption(self):
        p.validate_capture(self.payload(outcome="interrupted", reason="Power interruption"))

    def test_forfeit_direction(self):
        with self.assertRaises(ValueError): p.validate_capture(self.payload(outcome="forfeit_home", reason="Absent"))

    def test_digest_order(self):
        self.assertEqual(p.digest({"a": 1, "b": 2}), p.digest({"b": 2, "a": 1}))

    def test_digest_content(self):
        self.assertNotEqual(p.digest({"a": 1}), p.digest({"a": 2}))

    def test_command(self):
        p.validate_command({"key": "abcdefgh", "revision": 0, "operation": "save", "payload": {}, "signature": "a" * 64})

    def test_command_bad_revision(self):
        with self.assertRaises(ValueError): p.validate_command({"key": "abcdefgh", "revision": True,
            "operation": "save", "payload": {}, "signature": "a" * 64})

    def test_command_unknown_operation(self):
        with self.assertRaises(ValueError): p.validate_command({"key": "abcdefgh", "revision": 0,
            "operation": "approve", "payload": {}, "signature": "a" * 64})

    def test_period_bound(self):
        with self.assertRaises(ValueError): p.validate_capture(self.payload(periods=[{"home": 2, "away": 1}] * 101), "periods")


if __name__ == "__main__": unittest.main()
