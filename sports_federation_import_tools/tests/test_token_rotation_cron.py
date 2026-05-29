"""Tests for integration partner token rotation cron."""

from datetime import timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestTokenRotationCron(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["federation.integration.partner"].create(
            {
                "name": "Cron Test Partner",
                "code": "CRON_TEST_ROT",
            }
        )
        # Issue a token so auth_token is set
        cls.partner._issue_auth_token()
        # Reset to fresh state
        cls.partner.write(
            {
                "token_last_rotated_on": fields.Datetime.now(),
                "token_rotation_required": False,
            }
        )

    # ── helpers ──────────────────────────────────────────────────────────────

    def _run_cron(self):
        self.env["federation.integration.partner"]._cron_flag_stale_tokens()
        self.partner.invalidate_recordset()

    # ── tests ────────────────────────────────────────────────────────────────

    def test_stale_token_is_flagged(self):
        """Token older than max_days (default 90) is flagged for rotation."""
        old_date = fields.Datetime.now() - timedelta(days=91)
        self.partner.write(
            {"token_last_rotated_on": old_date, "token_rotation_required": False}
        )
        self._run_cron()
        self.assertTrue(self.partner.token_rotation_required)

    def test_fresh_token_is_not_flagged(self):
        """Token within max_days is not flagged."""
        self.partner.write(
            {
                "token_last_rotated_on": fields.Datetime.now(),
                "token_rotation_required": False,
            }
        )
        self._run_cron()
        self.assertFalse(self.partner.token_rotation_required)

    def test_null_rotation_date_is_flagged(self):
        """Partner with no rotation date on record is flagged."""
        self.partner.write(
            {"token_last_rotated_on": False, "token_rotation_required": False}
        )
        self._run_cron()
        self.assertTrue(self.partner.token_rotation_required)

    def test_custom_max_days_param_is_respected(self):
        """ir.config_parameter override for max_days is honoured."""
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.token_rotation_max_days", "10"
        )
        try:
            recent = fields.Datetime.now() - timedelta(days=15)
            self.partner.write(
                {"token_last_rotated_on": recent, "token_rotation_required": False}
            )
            self._run_cron()
            self.assertTrue(self.partner.token_rotation_required)
        finally:
            # Restore default so other tests are unaffected
            self.env["ir.config_parameter"].sudo().set_param(
                "sports_federation.token_rotation_max_days", "90"
            )

    def test_already_flagged_partner_is_skipped(self):
        """Cron does not toggle a partner that is already flagged."""
        old_date = fields.Datetime.now() - timedelta(days=200)
        self.partner.write(
            {"token_last_rotated_on": old_date, "token_rotation_required": True}
        )
        # Should run without error and leave flag as True
        self._run_cron()
        self.assertTrue(self.partner.token_rotation_required)
