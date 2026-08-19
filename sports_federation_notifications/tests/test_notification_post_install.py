from odoo.tests.common import TransactionCase, tagged

EXPECTED_TEMPLATES = [
    "template_federation_generic_contact",
    "template_federation_registration_reminder",
    "template_federation_season_registration_confirmed",
    "template_federation_season_registration_rejected",
    "template_federation_tournament_published",
    "template_federation_participant_confirmed",
    "template_federation_result_approved",
    "template_federation_result_contested",
    "template_federation_standing_frozen",
    "template_federation_finance_confirmed",
    "template_federation_referee_assigned",
    "template_federation_missing_data_notice",
]

EXPECTED_CRONS = [
    "ir_cron_notification_scan",
    "ir_cron_notification_log_retention",
]


@tagged("-at_install", "post_install", "sports_federation_notifications")
class TestNotificationPostInstall(TransactionCase):
    """Post-install smoke tests: verify that all notification data records
    required by the notifications module are correctly loaded."""

    def test_mail_templates_loaded(self):
        """All expected mail templates are present after installation."""
        module = "sports_federation_notifications"
        for xmlid_name in EXPECTED_TEMPLATES:
            xmlid = f"{module}.{xmlid_name}"
            record = self.env.ref(xmlid, raise_if_not_found=False)
            self.assertIsNotNone(
                record,
                f"Mail template '{xmlid}' was not found after installation.",
            )

    def test_cron_jobs_loaded(self):
        """All expected cron jobs are present after installation."""
        module = "sports_federation_notifications"
        for xmlid_name in EXPECTED_CRONS:
            xmlid = f"{module}.{xmlid_name}"
            record = self.env.ref(xmlid, raise_if_not_found=False)
            self.assertIsNotNone(
                record,
                f"Cron job '{xmlid}' was not found after installation.",
            )
