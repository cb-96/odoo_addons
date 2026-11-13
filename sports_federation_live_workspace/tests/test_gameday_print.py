from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.sports_federation_duty_coverage.tests.common import CoverageFixture

from odoo.addons.sports_federation_schedule_approval.planning_tokens import (
    with_published_planning_token,
)


@tagged("post_install", "-at_install", "sf_gameday_print")
class TestGamedayPrint(CoverageFixture, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.day = cls.match.schedule_publication_id.matchday_id
        cls.day.sudo().write({"event_timezone": "Europe/Brussels"})
        court = cls.env["federation.playing.area"].create(
            {"name": "Print Court 1", "venue_id": cls.day.venue_id.id}
        )
        slot = cls.env["federation.schedule.slot"].create(
            {
                "matchday_id": cls.day.id,
                "court_id": court.id,
                "start_datetime": "2026-06-15 16:00:00",
                "end_datetime": "2026-06-15 16:40:00",
            }
        )
        with_published_planning_token(cls.match.sudo()).write(
            {"published_slot_id": slot.id}
        )
        with_published_planning_token(cls.other_match.sudo()).write(
            {"schedule_publication_id": False, "published_slot_id": False}
        )
        cls.duty = cls.env["federation.match.club.referee.duty"].create(
            {
                "match_id": cls.match.id,
                "club_id": cls.club.id,
                "role": "table",
                "state": "open",
            }
        )

    def test_schedule_lists_published_match_in_event_time(self):
        values = self.day._gameday_print_values()
        self.assertEqual([row["match"] for row in values["rows"]], [self.match])
        row = values["rows"][0]
        self.assertEqual(row["time"], "18:00")
        self.assertEqual(row["court"], "Print Court 1")
        self.assertIn(row, values["grid"]["18:00"][row["court_id"]])
        self.assertTrue(
            any(self.club.display_name in item for item in row["officials"])
        )

    def test_club_duties_are_grouped_by_club(self):
        duties = self.day._gameday_print_values()["club_duties"]
        self.assertEqual(list(duties), [self.club.display_name])
        self.assertEqual(duties[self.club.display_name][0]["time"], "18:00")

    def test_print_actions(self):
        schedule = self.day.action_print_gameday_schedule()
        self.assertEqual(
            schedule["report_name"],
            "sports_federation_live_workspace.report_gameday_schedule",
        )
        sheets = self.day.action_print_gameday_scoresheets()
        self.assertEqual(
            sheets["report_name"], "sports_federation_rosters.report_match_scoresheet"
        )
        self.assertEqual(sheets["context"]["active_ids"], self.match.ids)

    def test_report_renders(self):
        html, _kind = self.env["ir.actions.report"]._render_qweb_html(
            "sports_federation_live_workspace.action_report_gameday_schedule",
            self.day.ids,
        )
        self.assertIn(b"Print Court 1", html)
        self.assertIn(b"Club duties", html)

    def test_unpublished_day_cannot_be_printed(self):
        self.day.sudo().write({"current_publication_id": False})
        with self.assertRaises(UserError):
            self.day.action_print_gameday_schedule()
