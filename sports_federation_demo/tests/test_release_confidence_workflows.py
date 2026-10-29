from io import BytesIO
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged
from werkzeug.datastructures import FileStorage


@tagged("-at_install", "post_install", "sf_release_confidence")
class TestReleaseConfidenceResultPolicy(TransactionCase):
    """Exercise result policy with ordinary, separately assigned accounts."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        users = cls.env["res.users"].with_context(no_reset_password=True)
        internal = cls.env.ref("base.group_user")
        manager = cls.env.ref("sports_federation_base.group_federation_manager")
        validator = cls.env.ref(
            "sports_federation_result_control.group_result_validator"
        )
        approver = cls.env.ref(
            "sports_federation_result_control.group_result_approver"
        )

        def make_user(name, login, groups):
            return users.create(
                {
                    "name": name,
                    "login": login,
                    "email": login,
                    "group_ids": [Command.set([internal.id, *groups])],
                }
            )

        cls.submitter = make_user(
            "Confidence Submitter", "confidence.submitter@example.invalid", [manager.id]
        )
        cls.validator_user = make_user(
            "Confidence Validator",
            "confidence.validator@example.invalid",
            [manager.id, validator.id],
        )
        cls.approver_user = make_user(
            "Confidence Approver",
            "confidence.approver@example.invalid",
            [manager.id, approver.id],
        )

        cls.season = cls.env["federation.season"].create(
            {
                "name": "Release Confidence Season",
                "code": "RCF26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.competition = cls.env["federation.competition"].create(
            {"name": "Release Confidence League", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Release Confidence Edition",
                "competition_id": cls.competition.id,
                "season_id": cls.season.id,
            }
        )
        rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Release Confidence Rules",
                "code": "RCF26",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Release Confidence Division",
                "season_id": cls.season.id,
                "competition_id": cls.competition.id,
                "edition_id": cls.edition.id,
                "rule_set_id": rule_set.id,
                "date_start": "2026-03-01",
            }
        )
        home_club = cls.env["federation.club"].create(
            {"name": "Confidence Home Club", "email": "home@example.invalid"}
        )
        away_club = cls.env["federation.club"].create(
            {"name": "Confidence Away Club", "email": "away@example.invalid"}
        )
        cls.home_team = cls.env["federation.team"].create(
            {
                "name": "Confidence Home Team",
                "club_id": home_club.id,
                "email": "home-team@example.invalid",
            }
        )
        cls.away_team = cls.env["federation.team"].create(
            {
                "name": "Confidence Away Team",
                "club_id": away_club.id,
                "email": "away-team@example.invalid",
            }
        )

    def _new_match(self):
        return self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.home_team.id,
                "away_team_id": self.away_team.id,
                "home_score": 2,
                "away_score": 1,
                "state": "done",
            }
        )

    def test_controlled_policy_requires_independent_result_review(self):
        self.edition.write({"workflow_mode": "controlled"})
        self.assertTrue(self.edition.result_verification_required)
        self.assertTrue(self.edition.result_approval_required)
        self.assertFalse(self.edition.result_self_verification_allowed)
        self.assertFalse(self.edition.result_self_approval_allowed)

        match = self._new_match()
        match.with_user(self.submitter).action_submit_result()
        self.assertEqual(match.result_state, "submitted")
        self.assertFalse(match.include_in_official_standings)
        with self.assertRaises(ValidationError):
            match.with_user(self.submitter).action_verify_result()

        match.with_user(self.validator_user).action_verify_result()
        self.assertEqual(match.result_state, "verified")
        self.assertFalse(match.include_in_official_standings)
        with self.assertRaises(ValidationError):
            match.with_user(self.validator_user).action_approve_result()

        match.with_user(self.approver_user).action_approve_result()
        self.assertEqual(match.result_state, "approved")
        self.assertTrue(match.include_in_official_standings)
        self.assertEqual(match.result_submitted_by_id, self.submitter)
        self.assertEqual(match.result_verified_by_id, self.validator_user)
        self.assertEqual(match.result_approved_by_id, self.approver_user)

    def test_simple_policy_completes_review_when_result_is_submitted(self):
        self.edition.write({"workflow_mode": "simple"})
        match = self._new_match()

        match.with_user(self.submitter).action_submit_result()

        self.assertEqual(match.result_state, "approved")
        self.assertTrue(match.include_in_official_standings)
        self.assertEqual(match.result_submitted_by_id, self.submitter)
        self.assertEqual(match.result_verified_by_id, self.submitter)
        self.assertEqual(match.result_approved_by_id, self.submitter)

    def test_result_approval_survives_notification_failure_and_safe_retry(self):
        self.edition.write({"workflow_mode": "controlled"})
        match = self._new_match()
        match.with_user(self.submitter).action_submit_result()
        match.with_user(self.validator_user).action_verify_result()
        template = self.env.ref(
            "sports_federation_notifications.template_federation_result_approved"
        )

        with patch.object(
            type(template),
            "send_mail",
            side_effect=RuntimeError("local notification transport unavailable"),
        ):
            match.with_user(self.approver_user).action_approve_result()

        self.assertEqual(match.result_state, "approved")
        self.assertTrue(match.include_in_official_standings)
        notification = self.env["federation.notification.log"].search(
            [
                ("target_model", "=", match._name),
                ("target_res_id", "=", match.id),
                ("notification_type", "=", "email"),
                ("state", "=", "failed"),
            ],
            order="id desc",
            limit=1,
        )
        self.assertTrue(notification)
        self.assertTrue(notification.operator_message)

        match_count = self.env["federation.match"].search_count(
            [("tournament_id", "=", self.tournament.id)]
        )
        notification.action_queue_retry()
        job = self.env["federation.operation.job"].search(
            [
                ("source_model", "=", notification._name),
                ("source_res_id", "=", notification.id),
            ],
            limit=1,
        )
        self.assertEqual(job.state, "pending")

        with patch.object(type(template), "send_mail", return_value=1):
            self.assertTrue(job._execute())

        notification.invalidate_recordset()
        job.invalidate_recordset()
        self.assertEqual(notification.state, "sent")
        self.assertEqual(job.state, "done")
        self.assertEqual(match.result_state, "approved")
        self.assertEqual(
            self.env["federation.match"].search_count(
                [("tournament_id", "=", self.tournament.id)]
            ),
            match_count,
        )

    def test_repeated_result_submission_does_not_create_a_second_result(self):
        self.edition.write({"workflow_mode": "controlled"})
        match = self._new_match()
        match.with_user(self.submitter).action_submit_result()
        submitted_on = match.result_submitted_on
        audit_count = len(match.result_audit_ids)

        with self.assertRaises(ValidationError):
            match.with_user(self.submitter).action_submit_result()

        match.invalidate_recordset()
        self.assertEqual(match.result_state, "submitted")
        self.assertEqual(match.result_submitted_on, submitted_on)
        self.assertEqual(len(match.result_audit_ids), audit_count)

    def test_unsupported_guardian_and_payer_accounts_are_denied(self):
        portal_club_group = self.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        role_type = self.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )
        guardian = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Unsupported Guardian Account",
                "login": "unsupported.guardian@example.invalid",
                "group_ids": [Command.set([self.env.ref("base.group_portal").id])],
            }
        )
        payer = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Unsupported Payer Account",
                "login": "unsupported.payer@example.invalid",
                "group_ids": [Command.set([portal_club_group.id])],
            }
        )
        club = self.env["federation.club"].create(
            {"name": "Unsupported External Accounts Club"}
        )
        self.env["federation.club.representative"].create(
            {
                "club_id": club.id,
                "partner_id": payer.partner_id.id,
                "user_id": payer.id,
                "role_type_id": role_type.id,
            }
        )
        player = self.env["federation.player"].create(
            {
                "first_name": "Unsupported",
                "last_name": "Guardian Scope",
                "club_id": club.id,
            }
        )
        upload = FileStorage(
            stream=BytesIO(b"signed approval"),
            filename="approval.pdf",
            content_type="application/pdf",
        )

        with self.assertRaises(AccessError):
            self.env["federation.player.parental.approval"]._portal_create_parental_approval(
                player,
                {"guardian_name": "Guardian", "approval_date": "2026-10-11"},
                upload,
                user=guardian,
            )

        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Unsupported Payer Fee",
                "code": "RC_PAYER",
                "category": "registration",
                "default_amount": 10.0,
            }
        )
        finance_event = self.env["federation.finance.event"].create(
            {
                "name": "Unsupported Payer Event",
                "fee_type_id": fee_type.id,
                "event_type": "charge",
                "amount": 10.0,
                "source_model": club._name,
                "source_res_id": club.id,
                "club_id": club.id,
            }
        )
        with self.assertRaises(AccessError):
            finance_event.with_user(payer).read(["amount"])

        self.assertEqual(
            self.env["federation.player.parental.approval"].search_count(
                [("player_id", "=", player.id)]
            ),
            0,
        )
        self.assertEqual(finance_event.state, "draft")