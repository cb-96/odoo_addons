"""Pure tests for the identity backfill plan and the renewal progress policy."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "sports_federation_member_services"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backfill = load("identity_backfill_policy", MODULE / "identity_backfill_policy.py")
renewal = load("renewal_policy", MODULE / "renewal_policy.py")
lifecycle = load("lifecycle_policy", MODULE / "lifecycle_policy.py")


def key_for(first, last, birth):
    return lifecycle.fingerprint((lifecycle.normal_name(first), lifecycle.normal_name(last), str(birth)))


def player(pid, first, last, birth="2012-01-01"):
    return {"id": pid, "first_name": first, "last_name": last, "birth_date": birth}


class BackfillPlanTests(unittest.TestCase):
    def test_a_unique_player_is_keyed(self):
        result = backfill.plan([player(1, "Ann", "Lee")], {}, key_for)
        self.assertEqual(result["to_key"], [(1, key_for("Ann", "Lee", "2012-01-01"))])
        self.assertEqual(result["candidates"], {})

    def test_players_that_look_the_same_are_never_keyed(self):
        result = backfill.plan([player(1, "Ann", "Lee"), player(2, "ANN", "lee")], {}, key_for)
        self.assertEqual(result["to_key"], [])
        self.assertEqual(list(result["candidates"].values()), [[1, 2]])

    def test_case_and_spacing_still_match(self):
        result = backfill.plan([player(1, "Zoe", "Van  Lee"), player(2, "ZOE", "van lee")], {}, key_for)
        self.assertEqual(len(result["candidates"]), 1)

    def test_accent_variants_are_not_matched_by_the_existing_normaliser(self):
        # Documented limitation: the shared duplicate guard casefolds but does not
        # strip accents, and the backfill deliberately uses the very same key.
        result = backfill.plan([player(1, "Zo\u00eb", "Lee"), player(2, "Zoe", "Lee")], {}, key_for)
        self.assertEqual(len(result["to_key"]), 2)
        self.assertEqual(result["candidates"], {})

    def test_a_player_matching_an_already_keyed_one_is_a_candidate(self):
        key = key_for("Ann", "Lee", "2012-01-01")
        result = backfill.plan([player(2, "Ann", "Lee")], {key: [1]}, key_for)
        self.assertEqual(result["to_key"], [])
        self.assertEqual(result["candidates"][key], [1, 2])

    def test_different_birth_dates_are_different_people(self):
        result = backfill.plan(
            [player(1, "Ann", "Lee", "2012-01-01"), player(2, "Ann", "Lee", "2013-02-02")], {}, key_for
        )
        self.assertEqual(len(result["to_key"]), 2)
        self.assertEqual(result["candidates"], {})

    def test_players_without_a_birth_date_are_only_counted(self):
        result = backfill.plan([player(1, "Ann", "Lee", None), player(2, "Bob", "Roe", False)], {}, key_for)
        self.assertEqual(result["needs_birth_date"], [1, 2])
        self.assertEqual(result["to_key"], [])
        self.assertEqual(result["candidates"], {})

    def test_the_plan_never_merges_anything(self):
        self.assertEqual(set(backfill.plan([], {}, key_for)), {"to_key", "candidates", "needs_birth_date"})


class RenewalProgressTests(unittest.TestCase):
    def test_not_a_renewal(self):
        self.assertEqual(renewal.progress(False, "draft", True, 0), ("none", []))

    def test_new_renewal_awaits_the_review_of_changes(self):
        step, blockers = renewal.progress(True, "draft", False, 0)
        self.assertEqual(step, "initiated")
        self.assertEqual(blockers, ["Record the review of changed information."])

    def test_reviewed_renewal_waits_for_documents(self):
        step, blockers = renewal.progress(True, "draft", True, 2)
        self.assertEqual(step, "compliance")
        self.assertEqual(blockers, ["2 required documents are still to verify."])
        self.assertIn("1 required document is", renewal.progress(True, "draft", True, 1)[1][0])

    def test_everything_in_place_is_ready_to_approve(self):
        self.assertEqual(renewal.progress(True, "draft", True, 0), ("ready", []))

    def test_a_merged_identity_blocks_the_renewal(self):
        step, blockers = renewal.progress(True, "draft", True, 0, identity_current=False)
        self.assertEqual(step, "initiated")
        self.assertIn("canonical identity", blockers[0])

    def test_finished_renewals(self):
        self.assertEqual(renewal.progress(True, "active", False, 5), ("approved", []))
        self.assertEqual(renewal.progress(True, "cancelled", False, 5), ("cancelled", []))

    def test_payment_never_blocks_approval(self):
        self.assertFalse(renewal.payment_note(False))
        self.assertFalse(renewal.payment_note("settled"))
        self.assertIn("does not block", renewal.payment_note("confirmed"))
        step, blockers = renewal.progress(True, "draft", True, 0)
        self.assertEqual((step, blockers), ("ready", []))


class ContractTests(unittest.TestCase):
    def test_repository_honours_the_identity_and_renewal_contract(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "ci/check_identity_renewal.py")], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
