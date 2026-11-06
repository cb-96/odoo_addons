from datetime import datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.sports_federation_scheduling.services.rest_capacity import (
    max_matches_with_rest,
)


@tagged("post_install", "-at_install", "sf_setup_flow")
class TestShortRestPublication(TransactionCase):
    def test_rest_capacity_counts_rows_a_team_can_use(self):
        start = datetime(2026, 11, 7, 9)
        rows = [
            (start + timedelta(minutes=40 * i), start + timedelta(minutes=40 * (i + 1)))
            for i in range(13)
        ]
        self.assertEqual(max_matches_with_rest(rows, 0), 13)
        self.assertEqual(max_matches_with_rest(rows, 40), 7)
        self.assertEqual(max_matches_with_rest(rows, 80), 5)

    def _draft_competition(self):
        Wizard = self.env["federation.practice.competition.wizard"]
        with patch.object(
            type(Wizard),
            "_publish",
            lambda wizard, edition, issues: {
                "published": 0,
                "waiting": [],
                "skipped": [],
            },
        ):
            wizard = Wizard.create(
                {
                    "name": "Short rest %s" % self.id(),
                    "division_count": 1,
                    "teams_per_division": 6,
                    "gameday_count": 1,
                    "first_gameday_today": False,
                    "first_gameday": fields.Date.context_today(Wizard)
                    + timedelta(days=30),
                }
            )
            wizard.action_create()
        edition = self.env["federation.competition.edition"].search(
            [("name", "=", "[Practice] %s" % wizard.name)], limit=1
        )
        schedule = self.env["federation.schedule"].search(
            [("edition_id", "=", edition.id)]
        )
        self.assertTrue(schedule)
        self.assertEqual(set(schedule.mapped("state")), {"draft"})
        # Every team plays five times on the single game day: far less than
        # ten hours between matches.
        schedule.write({"preferred_rest_minutes": 600})
        return edition, schedule

    def test_publish_asks_to_accept_short_rest_instead_of_failing(self):
        edition, schedule = self._draft_competition()
        action = edition.action_publish_competition_schedule()
        self.assertEqual(
            action.get("res_model"), "federation.schedule.publish.confirm.wizard"
        )
        confirm = self.env[action["res_model"]].browse(action["res_id"])
        self.assertEqual(confirm.warning_day_count, 1)
        self.assertIn("min rest", confirm.details_html)

        confirm.action_publish_others()
        self.assertEqual(schedule.state, "draft")

        confirm.reason = "Tournament format: back-to-back matches are expected."
        confirm.action_publish_all()
        self.assertEqual(schedule.state, "published")
        override = self.env["federation.schedule.change"].search(
            [("schedule_id", "=", schedule.id), ("command", "=", "warning_override")]
        )
        self.assertIn("back-to-back", " ".join(override.mapped("reason")))

    def test_generation_explains_days_where_rest_cannot_fit(self):
        edition, schedule = self._draft_competition()
        day = schedule.matchday_id
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {"edition_id": edition.id, "preferred_rest_minutes": 600}
        )
        wizard._onchange_edition_id()
        fixtures = day.allocation_ids.mapped("fixture_ids")
        messages = wizard._rest_shortfalls(
            fixtures, {"assignments": {day.id: fixtures.ids}}
        )
        self.assertEqual(len(messages), 1)
        self.assertIn(day.display_name, messages[0])

    def test_regeneration_updates_the_rest_of_a_reused_draft(self):
        edition, schedule = self._draft_competition()
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {"edition_id": edition.id, "preferred_rest_minutes": 15}
        )
        fixtures = schedule.matchday_id.allocation_ids.mapped("fixture_ids")
        reused = wizard._schedule_for_day(schedule.matchday_id, fixtures)
        self.assertEqual(reused, schedule)
        self.assertEqual(schedule.preferred_rest_minutes, 15)
