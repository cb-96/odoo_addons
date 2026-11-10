from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_player_availability")
class TestPlayerAvailability(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.context_today(cls.env["federation.club"])
        cls.club = cls.env["federation.club"].create(
            {"name": "Availability Club", "code": "AVL"}
        )
        cls.team = cls.env["federation.team"].create(
            {"name": "Availability Team", "club_id": cls.club.id, "gender": "male"}
        )
        season = cls.env["federation.season"].create(
            {
                "name": "Availability Season",
                "code": "AVLS",
                "date_start": today - timedelta(days=30),
                "date_end": today + timedelta(days=300),
            }
        )
        roster = cls.env["federation.team.roster"].create(
            {"team_id": cls.team.id, "season_id": season.id}
        )
        Player = cls.env["federation.player"]
        cls.with_email = Player.create(
            {
                "first_name": "Mail",
                "last_name": "Player",
                "gender": "male",
                "club_id": cls.club.id,
                "email": "mail.player@example.com",
            }
        )
        cls.without_email = Player.create(
            {
                "first_name": "Phone",
                "last_name": "Player",
                "gender": "male",
                "club_id": cls.club.id,
            }
        )
        for player in cls.with_email | cls.without_email:
            cls.env["federation.team.roster.line"].create(
                {"roster_id": roster.id, "player_id": player.id}
            )
        competition = cls.env["federation.competition"].create(
            {"name": "Availability Competition", "competition_type": "league"}
        )
        edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Availability Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        venue = cls.env["federation.venue"].create({"name": "Availability Venue"})
        cls.day = cls.env["federation.matchday"].create(
            {
                "name": "Availability Game Day",
                "edition_id": edition.id,
                "date": today + timedelta(days=7),
                "venue_id": venue.id,
            }
        )
        cls.Request = cls.env["federation.player.availability.request"]

    def test_clubs_must_switch_it_on(self):
        self.assertFalse(self.club.player_availability_enabled)
        with self.assertRaises(UserError):
            self.Request._open_request(self.team, self.day)
        self.assertEqual(self.Request._lineup_availability(self.team, self.day), {})

    def test_request_lists_roster_players_and_emails_those_with_an_address(self):
        self.club.player_availability_enabled = True
        request = self.Request._open_request(self.team, self.day)
        self.assertEqual(
            request.line_ids.player_id, self.with_email | self.without_email
        )
        self.assertEqual(request.pending_count, 2)
        self.assertEqual(request._send_invitations(), 1)
        self.assertEqual(request._send_invitations(), 0, "Players are invited once.")
        mail = self.env["mail.mail"].search(
            [("email_to", "=", "mail.player@example.com")], limit=1
        )
        self.assertIn("/availability/", mail.body_html)
        self.assertEqual(self.Request._open_request(self.team, self.day), request)

    def test_player_answers_through_the_personal_link(self):
        self.club.player_availability_enabled = True
        request = self.Request._open_request(self.team, self.day)
        line = request.line_ids.filtered(lambda item: item.player_id == self.with_email)
        found = self.env["federation.player.availability"]._from_token(
            line.access_token
        )
        self.assertEqual(found, line)
        self.assertFalse(
            self.env["federation.player.availability"]._from_token("x" * 30)
        )
        found._record_response("maybe", "only the morning")
        self.assertEqual(line.response, "maybe")
        self.assertEqual(line.answered_by, "player")
        with self.assertRaises(ValidationError):
            found._record_response("pending")
        answers = self.Request._lineup_availability(self.team, self.day)
        self.assertEqual(answers[self.with_email.id]["response"], "maybe")
        self.assertEqual(answers[self.with_email.id]["note"], "only the morning")

    def test_reminder_goes_only_to_players_without_an_answer(self):
        self.club.player_availability_enabled = True
        request = self.Request._open_request(self.team, self.day)
        request._send_invitations()
        self.assertEqual(
            request._send_invitations(only_unanswered=True, reminder=True), 1
        )
        request.line_ids.filtered(
            lambda item: item.player_id == self.with_email
        )._record_response("yes")
        self.assertEqual(
            request._send_invitations(only_unanswered=True, reminder=True), 0
        )

    def test_answers_close_after_the_game_day(self):
        self.club.player_availability_enabled = True
        request = self.Request._open_request(self.team, self.day)
        self.day.date = fields.Date.context_today(self.day) - timedelta(days=1)
        with self.assertRaises(ValidationError):
            request.line_ids[:1]._record_response("yes")
