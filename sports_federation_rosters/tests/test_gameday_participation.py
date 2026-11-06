from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_gameday_participation")
class TestGamedayParticipation(TransactionCase):
    """One roster per team gameday; players are crossed out per match.

    Scaled-down version of "14 on the gameday roster, 12 per match":
    3 players may be listed and 2 may play each match.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        club = cls.env["federation.club"].create({"name": "Gameday Club", "code": "GDC"})
        cls.team = cls.env["federation.team"].create(
            {"name": "Gameday Home", "club_id": club.id, "code": "GDH"}
        )
        cls.opponent = cls.env["federation.team"].create(
            {"name": "Gameday Away", "club_id": club.id, "code": "GDA"}
        )
        season = cls.env["federation.season"].create(
            {
                "name": "Gameday Season",
                "code": "GDS2024",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        tournament = cls.env["federation.tournament"].create(
            {
                "name": "Gameday Tournament",
                "code": "GDTOUR",
                "season_id": season.id,
                "date_start": "2024-01-01",
            }
        )
        Match = cls.env["federation.match"].with_context(skip_auto_match_sheets=True)
        cls.first_match, cls.second_match = [
            Match.create(
                {
                    "tournament_id": tournament.id,
                    "home_team_id": cls.team.id,
                    "away_team_id": cls.opponent.id,
                    "date_scheduled": kickoff,
                }
            )
            for kickoff in ("2024-06-15 10:00:00", "2024-06-15 14:00:00")
        ]
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Gameday Rules",
                "code": "GAMEDAY-RULES",
                "squad_min_size": 1,
                "gameday_roster_max_size": 3,
                "match_player_max_size": 2,
            }
        )
        cls.roster = cls.env["federation.team.roster"].create(
            {
                "name": "Gameday Season Roster",
                "team_id": cls.team.id,
                "season_id": season.id,
                "rule_set_id": cls.rule_set.id,
            }
        )
        cls.players = cls.env["federation.player"]
        cls.roster_lines = cls.env["federation.team.roster.line"]
        for index in range(4):
            player = cls.env["federation.player"].create(
                {
                    "name": f"Gameday Player {index}",
                    "first_name": "Gameday",
                    "last_name": f"Player {index}",
                    "gender": "male",
                }
            )
            cls.players |= player
            cls.roster_lines |= cls.env["federation.team.roster.line"].create(
                {"roster_id": cls.roster.id, "player_id": player.id}
            )
        cls.roster.action_activate()

    def _sheets(self):
        Sheet = self.env["federation.match.sheet"]
        first = Sheet.create(
            {
                "match_id": self.first_match.id,
                "team_id": self.team.id,
                "roster_id": self.roster.id,
                "side": "home",
            }
        )
        second = Sheet.create(
            {"match_id": self.second_match.id, "team_id": self.team.id, "side": "home"}
        )
        return first, second

    def _declare(self, sheet, count=3):
        self.env["federation.match.sheet.line"].create(
            [
                {
                    "match_sheet_id": sheet.id,
                    "player_id": line.player_id.id,
                    "roster_line_id": line.id,
                }
                for line in self.roster_lines[:count]
            ]
        )

    def _approved_gameday(self):
        first, second = self._sheets()
        self._declare(first)
        first.action_submit()
        if first.state == "submitted":
            first.action_approve()
        return first, second

    def test_gameday_roster_is_shared_without_starting_roles(self):
        first, second = self._approved_gameday()
        self.assertEqual(set((first | second).mapped("state")), {"approved"})
        self.assertEqual(second.line_ids.player_id, first.line_ids.player_id)
        self.assertFalse((first | second).line_ids.filtered("is_starter"))
        self.assertFalse((first | second).line_ids.filtered("is_substitute"))

    def test_gameday_roster_limit_is_enforced_on_submission(self):
        first, _second = self._sheets()
        self._declare(first, count=4)
        with self.assertRaisesRegex(ValidationError, "maximum is 3"):
            first.action_submit()

    def test_extra_players_must_be_crossed_out_per_match(self):
        first, second = self._approved_gameday()
        self.assertEqual(first.participant_count, 3)
        self.assertEqual(first.match_participant_limit, 2)
        self.assertTrue(first.participation_feedback)
        self.assertTrue(first.can_record_participation)

        with self.assertRaisesRegex(ValidationError, "at most 2 may play"):
            first.action_set_crossed_out([])

        first.action_set_crossed_out([self.players[0].id])
        second.action_set_crossed_out([self.players[2].id])

        self.assertEqual(first.participant_count, 2)
        self.assertFalse(first.participation_feedback)
        self.assertEqual(
            first.line_ids.filtered("crossed_out").player_id, self.players[0]
        )
        # The other match keeps its own choice; the gameday roster is unchanged.
        self.assertEqual(
            second.line_ids.filtered("crossed_out").player_id, self.players[2]
        )
        self.assertEqual(len(first.line_ids), 3)
        self.assertEqual(len(second.line_ids), 3)
        self.assertIn(
            "match_participation_updated",
            first.audit_event_ids.mapped("event_type"),
        )

    def test_players_can_be_restored_for_a_match(self):
        first, _second = self._approved_gameday()
        first.action_set_crossed_out([self.players[0].id])
        first.action_set_crossed_out([self.players[1].id])
        self.assertEqual(
            first.line_ids.filtered("crossed_out").player_id, self.players[1]
        )

    def test_only_gameday_players_can_be_crossed_out(self):
        first, _second = self._approved_gameday()
        with self.assertRaises(ValidationError):
            first.action_set_crossed_out([self.players[3].id])
        with self.assertRaises(ValidationError):
            first.action_set_crossed_out(["not-a-player"])
        with self.assertRaises(ValidationError):
            first.action_set_crossed_out(first.line_ids.player_id.ids)

    def test_draft_roster_cannot_cross_out(self):
        first, _second = self._sheets()
        self._declare(first)
        self.assertFalse(first.can_record_participation)
        with self.assertRaises(ValidationError):
            first.action_set_crossed_out([self.players[0].id])

    def test_crossed_out_player_cannot_have_playing_minutes(self):
        first, _second = self._approved_gameday()
        first.action_set_crossed_out([self.players[0].id])
        line = first.line_ids.filtered("crossed_out")
        with self.assertRaises(ValidationError):
            line.write({"left_minute": 10})

    def test_lock_requires_valid_match_participation(self):
        first, _second = self._approved_gameday()
        with self.assertRaisesRegex(ValidationError, "cannot be locked"):
            first.action_lock()
        first.action_set_crossed_out([self.players[0].id])
        first.action_lock()
        self.assertEqual(first.state, "locked")
        with self.assertRaises(ValidationError):
            first.action_set_crossed_out([self.players[1].id])

    def test_review_resync_keeps_match_specific_crossings(self):
        first, second = self._sheets()
        self._declare(first)
        first.action_submit()
        if first.state != "submitted":
            self.skipTest("Competition approves gameday rosters automatically.")
        second.action_set_crossed_out([self.players[1].id])
        first.action_approve()
        self.assertEqual(second.state, "approved")
        self.assertEqual(
            second.line_ids.filtered("crossed_out").player_id, self.players[1]
        )

    def test_rule_set_rejects_more_match_players_than_gameday_players(self):
        with self.assertRaises(ValidationError):
            self.env["federation.rule.set"].create(
                {
                    "name": "Invalid Gameday Rules",
                    "code": "BAD-GAMEDAY",
                    "gameday_roster_max_size": 12,
                    "match_player_max_size": 14,
                }
            )

    def test_sync_shares_draft_roster_with_other_matches(self):
        first, second = self._sheets()
        self._declare(first)
        first.action_sync_gameday_roster()
        self.assertEqual(second.line_ids.player_id, first.line_ids.player_id)
        self.assertEqual(second.state, "draft")
