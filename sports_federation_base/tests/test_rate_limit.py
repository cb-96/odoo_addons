from datetime import datetime, timedelta
from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestFederationRequestRateLimit(TransactionCase):
    def test_consume_blocks_after_policy_limit(self):
        service = self.env["federation.request.rate.limit"].sudo()
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.rate_limit.public_competitions_json.limit",
            2,
        )

        frozen_time = datetime(2026, 4, 18, 12, 0, 5)
        with patch.object(type(service), "_get_now", return_value=frozen_time):
            first = service.consume("public_competitions_json", "ip:198.51.100.10")
            second = service.consume("public_competitions_json", "ip:198.51.100.10")
            third = service.consume("public_competitions_json", "ip:198.51.100.10")

        self.assertTrue(first["allowed"])
        self.assertEqual(first["remaining"], 1)
        self.assertTrue(second["allowed"])
        self.assertEqual(second["remaining"], 0)
        self.assertFalse(third["allowed"])
        self.assertEqual(third["retry_after"], 55)

    def test_consume_resets_when_window_rolls_over(self):
        service = self.env["federation.request.rate.limit"].sudo()
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.rate_limit.public_team_feed.limit",
            1,
        )

        initial_time = datetime(2026, 4, 18, 12, 0, 0)
        rolled_time = initial_time + timedelta(seconds=61)
        with patch.object(
            type(service), "_get_now", side_effect=[initial_time, rolled_time]
        ):
            first = service.consume("public_team_feed", "ip:198.51.100.11")
            second = service.consume("public_team_feed", "ip:198.51.100.11")

        self.assertTrue(first["allowed"])
        self.assertTrue(second["allowed"])
        self.assertEqual(
            self.env["federation.request.rate.limit"].search_count(
                [
                    ("scope", "=", "public_team_feed"),
                    ("subject", "=", "ip:198.51.100.11"),
                ]
            ),
            2,
        )
