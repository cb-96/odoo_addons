from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_schedule_review_permissions")
@tagged("sf_release_focus")
class TestScheduleReviewPermissions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        users = cls.env["res.users"].with_context(no_reset_password=True)
        internal = cls.env.ref("base.group_user")
        planner_group = cls.env.ref(
            "sports_federation_scheduling.group_schedule_planner"
        )
        approver_group = cls.env.ref(
            "sports_federation_schedule_approval.group_schedule_approver"
        )
        manager_group = cls.env.ref("sports_federation_base.group_federation_manager")

        def make_user(name, login, groups):
            return users.create(
                {
                    "name": name,
                    "login": login,
                    "group_ids": [Command.set([internal.id, *groups])],
                }
            )

        cls.planner = make_user("Review Planner", "review.planner", [planner_group.id])
        cls.approver = make_user(
            "Independent Approver", "review.approver", [approver_group.id]
        )
        cls.manager = make_user("Review Manager", "review.manager", [manager_group.id])
        cls.unrelated = make_user("Unrelated User", "review.unrelated", [])

        season = cls.env["federation.season"].create(
            {
                "name": "Review Permission Season",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Review Permission League", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Review Permission Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        division = cls.env["federation.tournament"].create(
            {
                "name": "Review Permission Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2026-10-01",
            }
        )
        participants = cls.env["federation.participant.set"].create(
            {
                "name": "Review Permission Participants",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "state": "finalized",
            }
        )
        structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Review Permission Structure",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "participant_set_id": participants.id,
                "format_type": "custom",
                "state": "frozen",
            }
        )
        venue = cls.env["federation.venue"].create({"name": "Review Permission Venue"})
        matchday = cls.env["federation.matchday"].create(
            {
                "name": "Review Permission Match Day",
                "edition_id": cls.edition.id,
                "date": "2026-10-10",
                "venue_id": venue.id,
                "state": "scheduled",
            }
        )
        cls.schedule = cls.env["federation.schedule"].create(
            {
                "name": "Review Permission Schedule",
                "edition_id": cls.edition.id,
                "structure_id": structure.id,
                "matchday_id": matchday.id,
                "state": "ready_for_review",
                "revision": 1,
            }
        )
        roles = cls.env["federation.competition.role.assignment"]
        roles.create(
            {
                "edition_id": cls.edition.id,
                "user_id": cls.planner.id,
                "role": "schedule_planner",
            }
        )
        roles.create(
            {
                "edition_id": cls.edition.id,
                "user_id": cls.approver.id,
                "role": "schedule_approver",
            }
        )

    def setUp(self):
        super().setUp()
        self.schedule.state = "ready_for_review"
        self.review = (
            self.env["federation.schedule.approval.commands"]
            .with_user(self.planner)
            .start_review(self.schedule.id)
        )

    def _request_changes(self):
        self.env["federation.schedule.approval.commands"].with_user(
            self.approver
        ).request_changes(self.review.id, "Move the final to the main court.")

    def test_approver_can_submit_allowed_review_decision(self):
        self._request_changes()
        self.assertEqual(self.review.state, "changes_requested")
        self.assertEqual(self.review.reviewer_id, self.approver)
        self.assertTrue(self.review.reviewed_at)
        self.assertEqual(self.schedule.state, "changes_requested")

    def test_approver_cannot_alter_immutable_evidence_afterward(self):
        self._request_changes()
        with self.assertRaises(ValidationError):
            self.review.with_user(self.approver).write(
                {"assignment_snapshot": [{"fixture_id": 999}]}
            )
        with self.assertRaises(ValidationError):
            self.review.with_user(self.approver).write(
                {"review_note": "Rewritten after finalization"}
            )

    def test_manager_cannot_overwrite_finalized_decision(self):
        self._request_changes()
        with self.assertRaises(ValidationError):
            self.env["federation.schedule.approval.commands"].with_user(
                self.manager
            ).approve(self.review.id, "Manager override")
        with self.assertRaises(ValidationError):
            self.review.with_user(self.manager).write({"state": "approved"})

    def test_unrelated_user_cannot_read_or_modify_review(self):
        review = self.review.with_user(self.unrelated)
        with self.assertRaises(AccessError):
            review.read(["state"])
        with self.assertRaises(AccessError):
            review.write({"review_note": "Unauthorized change"})

    def test_direct_writes_to_protected_fields_are_rejected(self):
        review = self.review.with_user(self.approver)
        review.write({"review_note": "Prepared decision note"})
        self.assertEqual(self.review.review_note, "Prepared decision note")
        for values in (
            {"state": "approved"},
            {"reviewer_id": self.approver.id},
            {"reviewed_at": "2026-10-01 12:00:00"},
            {"submitted_revision": 99},
            {"snapshot_digest": "forged"},
        ):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                review.write(values)

    def test_submitting_planner_can_withdraw_pending_review(self):
        self.env["federation.schedule.approval.commands"].with_user(
            self.planner
        ).withdraw(self.review.id, "Calendar planning added another fixture.")
        self.assertEqual(self.review.state, "withdrawn")
        self.assertEqual(self.schedule.state, "changes_requested")
