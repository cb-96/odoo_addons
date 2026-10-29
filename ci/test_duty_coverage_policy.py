import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "coverage_policy",
    Path(__file__).resolve().parents[1]
    / "sports_federation_duty_coverage/coverage_policy.py",
)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


def row(**kw):
    return dict(
        role="head",
        active=True,
        accepted=False,
        eligible=True,
        present=False,
        completed=False,
        **kw
    )


class CoveragePolicyTests(unittest.TestCase):
    def test_empty_required_is_uncovered(self):
        self.assertEqual(policy.project({"head": 1}, [])["state"], "uncovered")

    def test_assignment_is_not_acceptance(self):
        self.assertEqual(policy.project({"head": 1}, [row()])["state"], "needs_action")

    def test_acceptance_is_not_eligibility(self):
        a = row()
        a.update(accepted=True, eligible=False)
        self.assertEqual(policy.project({"head": 1}, [a])["state"], "needs_action")

    def test_accepted_eligible_is_ready_not_present(self):
        a = row()
        a["accepted"] = True
        p = policy.project({"head": 1}, [a])
        self.assertEqual(p["state"], "ready")
        self.assertEqual(p["present"], 0)

    def test_wrong_role_cannot_fill_head(self):
        a = row()
        a.update(role="table", accepted=True)
        self.assertEqual(policy.project({"head": 1}, [a])["state"], "uncovered")

    def test_cancelled_does_not_count(self):
        a = row()
        a.update(active=False, accepted=True)
        self.assertEqual(policy.project({"head": 1}, [a])["assigned"], 0)

    def test_unknown_is_not_checked(self):
        self.assertEqual(policy.project({}, [], checked=False)["state"], "unchecked")

    def test_explicit_zero_is_not_required(self):
        self.assertEqual(policy.project({"head": 0}, [])["state"], "not_required")

    def test_pending_club_duty_blocks_ready(self):
        a = row()
        a["accepted"] = True
        self.assertEqual(
            policy.project({"head": 1}, [a], pending_duties=1)["state"], "needs_action"
        )

    def test_completed_separate(self):
        a = row()
        a.update(accepted=True, present=True, completed=True)
        p = policy.project({"head": 1}, [a])
        self.assertEqual((p["accepted"], p["present"], p["completed"]), (1, 1, 1))

    def test_multiple_required_roles(self):
        a = row()
        a["accepted"] = True
        b = dict(a, role="table")
        self.assertEqual(
            policy.project({"head": 1, "table": 1}, [a, b])["state"], "ready"
        )

    def test_role_shortfall(self):
        a = row()
        a["accepted"] = True
        p = policy.project({"head": 2}, [a])
        self.assertEqual(p["missing"]["head"], 1)
