from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase


class TestNotifications(TransactionCase):
    """Test cases for notification service."""

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        # Create test club
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Test Club",
                "code": "TC001",
                "email": "test@example.com",
            }
        )

    def test_log_creation(self):
        """Test creating a notification log."""
        log = self.env["federation.notification.log"].create(
            {
                "name": "Test Log",
                "notification_type": "email",
                "state": "pending",
            }
        )
        self.assertTrue(log.id)
        self.assertEqual(log.name, "Test Log")
        self.assertEqual(log.notification_type, "email")
        self.assertEqual(log.state, "pending")

    def test_send_email_template_creates_log(self):
        """Test that send_email_template creates a log entry."""
        service = self.env["federation.notification.service"]
        log = service.send_email_template(
            self.club,
            "sports_federation_notifications.template_federation_generic_contact",
            email_to="test@example.com",
            log_name="Test Email",
        )
        self.assertTrue(log.id)
        self.assertEqual(log.name, "Test Email")
        self.assertEqual(log.target_model, "federation.club")
        self.assertEqual(log.target_res_id, self.club.id)
        self.assertEqual(log.recipient_email, "test@example.com")
        self.assertEqual(log.notification_type, "email")
        self.assertIn(log.state, ("sent", "failed"))

    def test_missing_template_failure_is_typed_for_operators(self):
        """Missing templates should create a configuration failure with safe operator feedback."""
        service = self.env["federation.notification.service"]

        log = service.send_email_template(
            self.club,
            "sports_federation_notifications.template_missing_for_phase4",
            email_to="test@example.com",
            log_name="Missing Template",
        )

        self.assertEqual(log.state, "failed")
        self.assertEqual(log.failure_category, "configuration_error")
        self.assertIn("not available in this database", log.operator_message)
        self.assertFalse(log.message)

    def test_create_activity(self):
        """Test creating an activity and log."""
        service = self.env["federation.notification.service"]
        user = self.env.ref("base.user_admin")
        log = service.create_activity(
            self.club,
            user.id,
            "Test Activity Summary",
            note="Test note",
        )
        self.assertTrue(log.id)
        self.assertEqual(log.name, "Test Activity Summary")
        self.assertEqual(log.notification_type, "activity")
        self.assertIn(log.state, ("sent", "failed"))

    def test_cron_method_runs_without_error(self):
        """Test that cron method runs without error."""
        service = self.env["federation.notification.service"]
        try:
            service._cron_placeholder_notification_scan()
        except Exception as e:
            self.fail(f"Cron method raised exception: {e}")

    def test_notification_log_retention_purges_old_sent_records(self):
        """Retention should purge old sent logs without deleting recent failures."""
        old_log = self.env["federation.notification.log"].create(
            {
                "name": "Old Sent Log",
                "notification_type": "email",
                "state": "sent",
            }
        )
        failed_log = self.env["federation.notification.log"].create(
            {
                "name": "Recent Failed Log",
                "notification_type": "email",
                "state": "failed",
            }
        )

        old_create_date = fields.Datetime.to_string(
            fields.Datetime.to_datetime(fields.Datetime.now()) - timedelta(days=120)
        )
        self.env.cr.execute(
            "UPDATE federation_notification_log SET create_date = %s WHERE id = %s",
            [old_create_date, old_log.id],
        )
        self.env["federation.notification.log"].flush_model(["create_date"])

        deleted = self.env["federation.notification.log"]._purge_retained_logs()

        self.assertEqual(deleted, 1)
        self.assertFalse(old_log.exists())
        self.assertTrue(failed_log.exists())

    def test_suspension_activation_creates_notification_log(self):
        """Test that suspension activation creates notification log."""
        Suspension = self.env.get("federation.suspension")
        DisciplineCase = self.env.get("federation.disciplinary.case")
        if Suspension is None or DisciplineCase is None:
            self.skipTest("Discipline module is not installed in this test run.")

        player = self.env["federation.player"].create(
            {
                "first_name": "Suspended",
                "last_name": "Player",
                "club_id": self.club.id,
                "email": "suspended.player@example.com",
            }
        )
        case = DisciplineCase.create(
            {
                "name": "Suspension Notification Case",
                "subject_player_id": player.id,
                "summary": "Suspension notification coverage.",
            }
        )
        suspension = Suspension.create(
            {
                "name": "One Match Suspension",
                "case_id": case.id,
                "player_id": player.id,
                "date_start": "2026-07-01",
                "date_end": "2026-07-07",
                "notes": "Activated during notification test.",
            }
        )

        suspension.action_activate()

        log = self.env["federation.notification.log"].search(
            [
                ("target_model", "=", "federation.suspension"),
                ("target_res_id", "=", suspension.id),
                ("name", "=", "Suspension issued: One Match Suspension"),
            ],
            limit=1,
        )
        self.assertTrue(log)
        self.assertIn(log.state, ("sent", "failed"))
        self.assertNotIn("[stub]", log.name)
        self.assertIn("suspended.player@example.com", log.recipient_email)
        self.assertIn("test@example.com", log.recipient_email)

    def test_season_registration_confirm_creates_notification_log(self):
        """Test that season registration confirm creates notification log."""
        portal_group = self.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        role_type = self.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )
        season = self.env["federation.season"].create(
            {
                "name": "Notification Season",
                "code": "NOTIFSEASON",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        team = self.env["federation.team"].create(
            {
                "name": "Notification Team",
                "club_id": self.club.id,
                "code": "NOTIFTEAM",
            }
        )
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Notification Portal User",
                    "login": "notification.portal.user@example.com",
                    "email": "notification.portal.user@example.com",
                    "group_ids": [(6, 0, [portal_group.id])],
                }
            )
        )
        self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": user.partner_id.id,
                "user_id": user.id,
                "role_type_id": role_type.id,
            }
        )

        registration = (
            self.env["federation.season.registration"]
            .with_user(user)
            .create(
                {
                    "season_id": season.id,
                    "team_id": team.id,
                }
            )
        )
        registration.with_user(user).action_submit()
        registration.with_user(user).action_confirm()

        log = self.env["federation.notification.log"].search(
            [
                ("target_model", "=", "federation.season.registration"),
                ("target_res_id", "=", registration.id),
                (
                    "template_xmlid",
                    "=",
                    "sports_federation_notifications.template_federation_season_registration_confirmed",
                ),
            ],
            limit=1,
        )
        self.assertTrue(log)
        self.assertIn(log.state, ("sent", "failed"))

    def test_season_registration_reject_creates_notification_log(self):
        """Test that season registration reject creates notification log."""
        portal_group = self.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        role_type = self.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )
        season = self.env["federation.season"].create(
            {
                "name": "Rejected Notification Season",
                "code": "REJNOTIF",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        team = self.env["federation.team"].create(
            {
                "name": "Rejected Notification Team",
                "club_id": self.club.id,
                "code": "REJTEAM",
            }
        )
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Rejected Notification User",
                    "login": "rejected.notification.user@example.com",
                    "email": "rejected.notification.user@example.com",
                    "group_ids": [(6, 0, [portal_group.id])],
                }
            )
        )
        self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": user.partner_id.id,
                "user_id": user.id,
                "role_type_id": role_type.id,
            }
        )

        registration = (
            self.env["federation.season.registration"]
            .with_user(user)
            .create(
                {
                    "season_id": season.id,
                    "team_id": team.id,
                }
            )
        )
        registration.with_user(user).action_submit()
        registration.with_user(user).action_reject("Missing supporting document")

        log = self.env["federation.notification.log"].search(
            [
                ("target_model", "=", "federation.season.registration"),
                ("target_res_id", "=", registration.id),
                (
                    "template_xmlid",
                    "=",
                    "sports_federation_notifications.template_federation_season_registration_rejected",
                ),
            ],
            limit=1,
        )
        self.assertTrue(log)
        self.assertIn(log.state, ("sent", "failed"))
        self.assertEqual(registration.rejection_reason, "Missing supporting document")

    def test_referee_shortage_alert_creates_notification_log(self):
        """Test that referee shortage alert creates notification log."""
        season = self.env["federation.season"].create(
            {
                "name": "Notification Match Season",
                "code": "NMSEASON",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        home_team = self.env["federation.team"].create(
            {
                "name": "Notification Home Team",
                "club_id": self.club.id,
                "code": "NMHT",
            }
        )
        away_club = self.env["federation.club"].create(
            {
                "name": "Notification Away Club",
                "code": "NMAC",
            }
        )
        away_team = self.env["federation.team"].create(
            {
                "name": "Notification Away Team",
                "club_id": away_club.id,
                "code": "NMAT",
            }
        )
        tournament = self.env["federation.tournament"].create(
            {
                "name": "Notification Match Tournament",
                "code": "NMT",
                "season_id": season.id,
                "date_start": "2026-06-01",
            }
        )
        match = self.env["federation.match"].create(
            {
                "tournament_id": tournament.id,
                "home_team_id": home_team.id,
                "away_team_id": away_team.id,
            }
        )

        dispatcher = self.env["federation.notification.dispatcher"]
        dispatcher.send_referee_shortage_alert(match)

        log = self.env["federation.notification.log"].search(
            [
                ("target_model", "=", "federation.match"),
                ("target_res_id", "=", match.id),
                ("name", "like", "Referee shortage"),
            ],
            limit=1,
        )
        self.assertTrue(log)
        self.assertIn(log.state, ("sent", "failed"))
