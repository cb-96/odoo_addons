from unittest.mock import patch

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_player_parental_overview")
class TestPlayerParentalOverview(TransactionCase):
    """The /my/players overview mirrors the roster rule for players under 16."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.today = fields.Date.context_today(cls.env["federation.player"])
        group = cls.env.ref("sports_federation_portal.group_federation_portal_club")
        role = cls.env.ref("sports_federation_portal.role_type_competition_contact")
        cls.club = cls.env["federation.club"].create(
            {"name": "Overview Club", "code": "OVC"}
        )
        cls.other_club = cls.env["federation.club"].create(
            {"name": "Overview Rivals", "code": "OVR"}
        )
        cls.user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Overview Representative",
                    "login": "overview.rep@example.com",
                    "group_ids": [(6, 0, [group.id])],
                }
            )
        )
        cls.env["federation.club.representative"].create(
            {
                "club_id": cls.club.id,
                "partner_id": cls.user.partner_id.id,
                "user_id": cls.user.id,
                "role_type_id": role.id,
            }
        )
        cls.senior_team = cls.env["federation.team"].create(
            {
                "name": "Overview Senior Men",
                "club_id": cls.club.id,
                "category": "senior",
                "gender": "male",
            }
        )
        season = cls.env["federation.season"].create(
            {
                "name": "Overview Season",
                "date_start": cls.today - relativedelta(months=2),
                "date_end": cls.today + relativedelta(months=8),
            }
        )
        cls.roster = cls.env["federation.team.roster"].create(
            {"team_id": cls.senior_team.id, "season_id": season.id}
        )

    def _player(self, name, years, club=None, on_senior_roster=False):
        player = self.env["federation.player"].create(
            {
                "first_name": name,
                "last_name": "Overview",
                "club_id": (club or self.club).id,
                "birth_date": (
                    self.today - relativedelta(years=years, days=30) if years else False
                ),
            }
        )
        if on_senior_roster:
            # The overview must flag a minor who is already on a senior
            # roster without a valid approval (for instance after the
            # approval lapsed). Roster lines now refuse such players, so the
            # line is created without the eligibility check on purpose.
            Line = self.env["federation.team.roster.line"]
            with patch.object(
                type(Line), "_validate_player_eligibility", lambda self: None
            ):
                Line.create({"roster_id": self.roster.id, "player_id": player.id})
        return player

    def _approval(self, player, valid_until=None, verify=False, **values):
        approval = self.env["federation.player.parental.approval"].create(
            dict(
                {
                    "player_id": player.id,
                    "guardian_name": "Parent",
                    "approval_date": self.today,
                    "valid_until": valid_until,
                    "approval_document": b"c2lnbmVk",
                },
                **values,
            )
        )
        if verify:
            approval.action_verify()
        return approval

    def _overview(self, *players, **kwargs):
        players = self.env["federation.player"].concat(*players)
        return self.env["federation.player.parental.approval"]._portal_player_overview(
            players, user=self.user, **kwargs
        )

    def _line(self, player, **kwargs):
        return self._overview(player, **kwargs)["by_player"][player.id]

    def test_minor_on_a_senior_roster_without_approval_needs_it_now(self):
        player = self._player("Nowa", 14, on_senior_roster=True)
        line = self._line(player)
        self.assertEqual(line["key"], "missing")
        self.assertEqual(line["level"], "danger")
        self.assertTrue(line["needs_action"])
        self.assertEqual(line["row_class"], "table-danger")
        self.assertIn("Overview Senior Men", line["detail"])

    def test_minor_outside_a_senior_roster_would_need_it(self):
        player = self._player("Later", 14)
        line = self._line(player)
        self.assertEqual(line["key"], "missing")
        self.assertEqual(line["level"], "warning")
        self.assertTrue(line["needs_action"])
        self.assertEqual(line["row_class"], "table-warning")

    def test_verified_approval_covering_today_is_not_flagged(self):
        player = self._player("Valid", 15, on_senior_roster=True)
        self._approval(
            player, valid_until=self.today + relativedelta(years=1), verify=True
        )
        line = self._line(player)
        self.assertEqual(line["key"], "approved")
        self.assertFalse(line["needs_action"])
        self.assertEqual(line["row_class"], "")

    def test_approval_that_expires_soon_is_called_out(self):
        player = self._player("Soon", 15)
        self._approval(
            player, valid_until=self.today + relativedelta(days=10), verify=True
        )
        line = self._line(player)
        self.assertEqual(line["key"], "expiring")
        self.assertFalse(line["needs_action"])

    def test_uploaded_approval_waits_for_the_federation(self):
        player = self._player("Wait", 15, on_senior_roster=True)
        self._approval(player)
        line = self._line(player)
        self.assertEqual(line["key"], "pending")
        self.assertFalse(line["needs_action"])

    def test_replacement_request_needs_action_and_shows_the_note(self):
        player = self._player("Again", 15)
        approval = self._approval(player, review_note="Signature is missing.")
        approval.action_request_replacement()
        line = self._line(player)
        self.assertEqual(line["key"], "replacement")
        self.assertTrue(line["needs_action"])
        self.assertIn("Signature is missing.", line["detail"])

    def test_expired_approval_needs_a_new_one(self):
        player = self._player("Old", 15)
        self._approval(
            player,
            valid_until=self.today - relativedelta(days=1),
            verify=True,
            approval_date=self.today - relativedelta(days=10),
        )
        line = self._line(player)
        self.assertEqual(line["key"], "expired")
        self.assertTrue(line["needs_action"])

    def test_adults_and_unknown_birth_dates(self):
        adult = self._player("Adult", 30)
        unknown = self._player("Unknown", 0)
        overview = self._overview(adult, unknown)
        self.assertEqual(overview["by_player"][adult.id]["key"], "not_required")
        self.assertFalse(overview["by_player"][adult.id]["show_badge"])
        self.assertEqual(overview["by_player"][unknown.id]["key"], "no_birth_date")
        self.assertEqual(overview["counts"]["no_birth_date"], 1)
        self.assertEqual(overview["counts"]["under_age"], 0)

    def test_the_reference_date_decides_whether_approval_is_needed(self):
        player = self._player("Grows", 15)
        self.assertEqual(self._line(player)["key"], "missing")
        later = self.today + relativedelta(years=2)
        self.assertEqual(
            self._line(player, reference_date=later)["key"], "not_required"
        )

    def test_counts_tiles_and_bar_add_up(self):
        now = self._player("A", 14, on_senior_roster=True)
        later = self._player("B", 13)
        approved = self._player("C", 15)
        self._approval(approved, verify=True)
        waiting = self._player("D", 15)
        self._approval(waiting)
        adult = self._player("E", 40)
        overview = self._overview(now, later, approved, waiting, adult)
        counts = overview["counts"]
        self.assertEqual(counts["under_age"], 4)
        self.assertEqual(counts["needed_now"], 1)
        self.assertEqual(counts["needed_later"], 1)
        self.assertEqual(counts["needs_action"], 2)
        self.assertEqual(counts["pending"], 1)
        self.assertEqual(counts["approved"], 1)
        self.assertEqual(sum(segment["count"] for segment in overview["bar"]), 4)
        self.assertEqual(
            {tile["label"]: tile["count"] for tile in overview["tiles"]}["Needed now"],
            1,
        )

    def test_players_of_other_clubs_are_not_described(self):
        foreign = self._player("Foreign", 14, club=self.other_club)
        overview = self._overview(foreign)
        self.assertNotIn(foreign.id, overview["by_player"])
        self.assertEqual(overview["counts"]["total"], 0)
