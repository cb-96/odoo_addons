from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.sports_federation_officiating import (
    duty_exact_solver,
    duty_explanations,
)

COMMAND = {"club_duty_policy_command": True}


@tagged("post_install", "-at_install", "sf_officiating", "sf_club_duty_planning")
class TestClubDutyPlanningGovernance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Policy = cls.env["federation.club.duty.policy"]
        cls.Policy.search([("state", "=", "active")]).with_context(**COMMAND).write(
            {"state": "retired"}
        )
        cls.user = new_test_user(
            cls.env,
            login="sf_duty_policy_reader",
            groups="base.group_user,sports_federation_base.group_federation_user",
        )

    def _draft(self, **values):
        return self.Policy.create(dict({"name": "Default duties"}, **values))

    def test_activation_numbers_versions_and_retires_previous(self):
        first = self._draft()
        first.action_activate()
        self.assertEqual((first.state, first.version), ("active", 1))
        second = self._draft(allow_fallback=True)
        second.action_activate()
        self.assertEqual((second.state, second.version), ("active", 2))
        self.assertEqual(first.state, "retired")
        self.assertEqual(second.previous_id, first)
        self.assertEqual(self.Policy._active_for_season(self.env["federation.season"]), second)

    def test_active_version_is_read_only(self):
        policy = self._draft()
        policy.action_activate()
        with self.assertRaises(UserError):
            policy.write({"allow_fallback": True})
        policy.write({"notes": "Reviewed with the clubs."})
        with self.assertRaises(UserError):
            policy.unlink()

    def test_lifecycle_fields_need_commands(self):
        policy = self._draft()
        with self.assertRaises(UserError):
            policy.write({"state": "active"})
        with self.assertRaises(UserError):
            self.Policy.create({"name": "Forged", "version": 7})

    def test_new_version_starts_as_linked_draft(self):
        policy = self._draft(officials_per_match=2)
        policy.action_activate()
        action = policy.action_new_version()
        draft = self.Policy.browse(action["res_id"])
        self.assertEqual((draft.state, draft.version), ("draft", 0))
        self.assertEqual(draft.previous_id, policy)
        self.assertEqual(draft.review_options(), policy.review_options())

    def test_federation_user_cannot_manage_policies_or_read_live_runs(self):
        policy = self._draft()
        with self.assertRaises(AccessError):
            self.Policy.with_user(self.user).create({"name": "Not allowed"})
        with self.assertRaises(AccessError):
            policy.with_user(self.user).action_activate()
        with self.assertRaises(AccessError):
            self.env["federation.club.duty.live.run"].with_user(self.user).search([])

    def test_live_run_state_needs_rollback_command(self):
        schedule = self.env["federation.schedule"].search([], limit=1)
        if not schedule:
            self.skipTest("No schedule available in this database.")
        run = self.env["federation.club.duty.live.run"].create(
            {"schedule_id": schedule.id, "applied_duty_count": 0}
        )
        with self.assertRaises(UserError):
            run.write({"state": "rolled_back"})
        self.assertTrue(run.rollback_blockers)
        with self.assertRaises(UserError):
            run.action_rollback()

    def test_exact_solver_availability_is_reported(self):
        policy = self._draft(solver="exact")
        self.assertEqual(
            policy.exact_solver_available, duty_exact_solver.exact_available()
        )

    def test_capacity_conflicts_get_suggested_fixes(self):
        detail = {
            "code": "capacity_conflict",
            "rejected": {3: "simultaneous capacity 1 would be exceeded"},
        }
        codes = duty_explanations.suggestions(detail, {"avoid": True, "fallback": False})
        self.assertEqual(
            codes,
            [
                "raise_capacity",
                "shorten_buffers",
                "allow_fallback",
                "move_fixture",
                "assign_referee",
            ],
        )
        review = self.env["federation.schedule.club.duty.review"]
        for code in duty_explanations.SUGGESTION_CODES:
            self.assertNotEqual(review._suggestion_text(code), code)
