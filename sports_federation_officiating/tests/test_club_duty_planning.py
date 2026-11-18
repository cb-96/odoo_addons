"""Database coverage for draft planning and publication handoff."""

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .test_auto_club_duty_assignment import TestAutoClubDutyAssignment


@tagged("post_install", "-at_install", "sf_club_duty_planning")
class TestClubDutyPlanning(TestAutoClubDutyAssignment):
    def _review(self, count=2):
        schedule = self.matches[0].schedule_publication_id.schedule_id
        wizard = self.env["federation.schedule.club.duty.review"].create(
            {
                "schedule_ids": [fields.Command.set(schedule.ids)],
                "officials_per_match": count,
                "allow_fallback": True,
            }
        )
        wizard.action_preview()
        return schedule, wizard

    def test_preview_and_apply_do_not_create_or_open_duties(self):
        schedule, wizard = self._review()
        self.assertEqual(wizard.issue_count, 0)
        wizard.action_apply()
        self.assertTrue(schedule.club_duty_plan)
        self.assertFalse(
            self.env["federation.match.club.referee.duty"].search(
                [("match_id", "in", self.matches.ids)]
            )
        )

    def test_publication_consumes_plan_once(self):
        schedule, wizard = self._review()
        wizard.action_apply()
        commands = self.env["federation.schedule.approval.commands"]
        first = commands._ensure_club_duties(self.matches)
        self.assertEqual(len(first), 6)
        self.assertEqual(set(first.mapped("state")), {"open"})
        self.assertFalse(commands._ensure_club_duties(self.matches))

    def test_policy_change_requires_new_preview(self):
        schedule, wizard = self._review()
        wizard.officials_per_match = 3
        with self.assertRaises(UserError):
            wizard.action_apply()
        wizard.action_preview()
        wizard.action_apply()
        self.assertEqual(schedule.club_duty_policy["count"], 3)

    def test_changed_slot_invalidates_preview_and_plan(self):
        schedule, wizard = self._review()
        wizard.action_apply()
        slot = schedule.assignment_ids[0].slot_id
        slot.write({"end_datetime": fields.Datetime.add(slot.end_datetime, minutes=5)})
        self.assertTrue(schedule.club_duty_review_required)
        with self.assertRaises(UserError):
            wizard.action_apply()
        with self.assertRaises(UserError):
            self.env["federation.schedule.approval.commands"]._ensure_club_duties(
                self.matches
            )

    def test_no_rule_requirement_means_no_proposed_duties(self):
        schedule, wizard = self._review(count=0)
        self.assertFalse(wizard.preview[str(schedule.id)]["rows"])

    def test_existing_official_is_not_duplicated(self):
        referee = self.env["federation.referee"].create({"name": "Preserved official"})
        self.env["federation.match.referee"].create(
            {"match_id": self.matches[0].id, "referee_id": referee.id, "role": "head"}
        )
        schedule, wizard = self._review()
        wizard.action_apply()
        duties = self.env["federation.schedule.approval.commands"]._ensure_club_duties(
            self.matches
        )
        self.assertEqual(len(duties), 5)
        self.assertFalse(
            duties.filtered(
                lambda d: d.match_id == self.matches[0] and d.role == "head"
            )
        )

    def test_missing_club_blocks_application(self):
        schedule, wizard = self._review()
        fixture = schedule.assignment_ids[0].fixture_id
        fixture.away_team_id = False
        wizard.action_preview()
        self.assertGreater(wizard.issue_count, 0)
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_new_existing_assignment_invalidates_review(self):
        schedule, wizard = self._review()
        referee = self.env["federation.referee"].create({"name": "Late official"})
        self.env["federation.match.referee"].create(
            {"match_id": self.matches[0].id, "referee_id": referee.id, "role": "head"}
        )
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_governed_run_applies_and_rolls_back_draft_plan(self):
        schedule = self.matches[0].schedule_publication_id.schedule_id
        run = self.env["federation.schedule.plan.run"].create(
            {
                "schedule_id": schedule.id,
                "plan_type": "club_duty",
                "configuration": {
                    "officials_per_match": 2,
                    "avoid_playing": True,
                    "allow_fallback": True,
                    "preserve_existing": True,
                },
            }
        )

        run.action_prepare()
        self.assertEqual(run.state, "ready")
        self.assertTrue(run.proposal["rows"])

        run.action_apply()
        self.assertEqual(run.state, "applied")
        self.assertTrue(schedule.club_duty_plan)

        run.action_rollback()
        self.assertEqual(run.state, "rolled_back")
        self.assertFalse(schedule.club_duty_policy)
        self.assertFalse(schedule.club_duty_plan)
        self.assertFalse(schedule.club_duty_signature)

    def test_governed_run_rejects_changed_duty_geometry(self):
        schedule = self.matches[0].schedule_publication_id.schedule_id
        run = self.env["federation.schedule.plan.run"].create(
            {
                "schedule_id": schedule.id,
                "plan_type": "club_duty",
                "configuration": {
                    "officials_per_match": 2,
                    "allow_fallback": True,
                },
            }
        )
        run.action_prepare()
        slot = schedule.assignment_ids[0].slot_id
        slot.end_datetime = fields.Datetime.add(slot.end_datetime, minutes=5)

        with self.assertRaises(UserError):
            run.action_apply()

        self.assertEqual(run.state, "ready")
        self.assertFalse(schedule.club_duty_plan)
