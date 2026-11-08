from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_club_rank")
class TestClubRank(TransactionCase):
    """Playing up, promotion after two matches and no playing down."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create({"name": "Rank Club", "code": "RKC"})
        cls.other_club = cls.env["federation.club"].create(
            {"name": "Rank Rivals", "code": "RKR"}
        )
        Team = cls.env["federation.team"]
        cls.team_a = Team.create(
            {"name": "Rank Club A", "club_id": cls.club.id, "gender": "male"}
        )
        cls.team_b = Team.create(
            {"name": "Rank Club B", "club_id": cls.club.id, "gender": "male"}
        )
        cls.rival = Team.create(
            {"name": "Rank Rivals", "club_id": cls.other_club.id, "gender": "male"}
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Rank Season",
                "code": "RKS",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Rank Division",
                "code": "RKD",
                "season_id": cls.season.id,
                "date_start": "2026-09-01",
            }
        )
        Roster = cls.env["federation.team.roster"]
        cls.roster_a = Roster.create(
            {"team_id": cls.team_a.id, "season_id": cls.season.id}
        )
        cls.roster_b = Roster.create(
            {"team_id": cls.team_b.id, "season_id": cls.season.id}
        )
        Player = cls.env["federation.player"]
        cls.a_player = Player.create(
            {"first_name": "Anna", "last_name": "Top", "gender": "male"}
        )
        cls.b_player = Player.create(
            {"first_name": "Bart", "last_name": "Second", "gender": "male"}
        )
        Line = cls.env["federation.team.roster.line"]
        cls.a_line = Line.create(
            {"roster_id": cls.roster_a.id, "player_id": cls.a_player.id}
        )
        cls.b_line = Line.create(
            {"roster_id": cls.roster_b.id, "player_id": cls.b_player.id}
        )

    def _played_match(self, kickoff, roster, line, crossed_out=False):
        """A done match whose approved line-up lists ``line``'s player."""
        match = (
            self.env["federation.match"]
            .with_context(skip_auto_match_sheets=True)
            .create(
                {
                    "tournament_id": self.tournament.id,
                    "home_team_id": roster.team_id.id,
                    "away_team_id": self.rival.id,
                    "date_scheduled": kickoff,
                    "home_score": 1,
                    "away_score": 0,
                    "state": "done",
                }
            )
        )
        sheet = self.env["federation.match.sheet"].create(
            {
                "match_id": match.id,
                "team_id": roster.team_id.id,
                "roster_id": roster.id,
                "side": "home",
            }
        )
        self.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": sheet.id,
                "player_id": line.player_id.id,
                "roster_line_id": line.id,
                "crossed_out": crossed_out,
            }
        )
        sheet.write({"state": "approved"})
        self.env.invalidate_all()
        return match, sheet

    def _promotions(self, player):
        return self.env["federation.club.rank.promotion"].search(
            [("player_id", "=", player.id)]
        )

    def test_rank_is_read_from_the_team_name(self):
        self.assertEqual(self.team_a.club_rank, 1)
        self.assertEqual(self.team_b.club_rank, 2)
        self.assertEqual(self.rival.club_rank, 0)

    def test_lower_team_player_can_play_up(self):
        line = self.env["federation.team.roster.line"].create(
            {"roster_id": self.roster_a.id, "player_id": self.b_player.id}
        )
        self.assertIn("Rank Club B", line.club_rank_note)
        self.assertNotIn(self.b_player, self.roster_a.club_rank_blocked_player_ids)

    def test_higher_team_player_cannot_play_down(self):
        self.assertIn(self.a_player, self.roster_b.club_rank_blocked_player_ids)
        with self.assertRaises(ValidationError):
            self.env["federation.team.roster.line"].create(
                {"roster_id": self.roster_b.id, "player_id": self.a_player.id}
            )

    def test_two_matches_promote_the_player(self):
        up_line = self.env["federation.team.roster.line"].create(
            {"roster_id": self.roster_a.id, "player_id": self.b_player.id}
        )
        self._played_match("2026-10-03 10:00:00", self.roster_a, up_line)
        self.assertFalse(self._promotions(self.b_player))

        _match, sheet = self._played_match("2026-10-10 10:00:00", self.roster_a, up_line)
        promotion = self._promotions(self.b_player)
        self.assertEqual(promotion.to_team_id, self.team_a)
        self.assertEqual(promotion.from_team_id, self.team_b)
        self.assertEqual(promotion.match_id, sheet.match_id)
        self.assertIn(self.b_player, self.roster_b.club_rank_blocked_player_ids)
        self.assertFalse(up_line.club_rank_note)

    def test_crossed_out_matches_do_not_count(self):
        up_line = self.env["federation.team.roster.line"].create(
            {"roster_id": self.roster_a.id, "player_id": self.b_player.id}
        )
        self._played_match("2026-10-03 10:00:00", self.roster_a, up_line)
        self._played_match(
            "2026-10-10 10:00:00", self.roster_a, up_line, crossed_out=True
        )
        self.assertFalse(self._promotions(self.b_player))

    def test_warning_before_the_deciding_match(self):
        up_line = self.env["federation.team.roster.line"].create(
            {"roster_id": self.roster_a.id, "player_id": self.b_player.id}
        )
        service = self.env["federation.club.rank.service"]
        self.assertEqual(
            service.promotion_warnings(self.roster_a, self.b_player, 1), []
        )
        self.assertTrue(service.promotion_warnings(self.roster_a, self.b_player, 2))
        self._played_match("2026-10-03 10:00:00", self.roster_a, up_line)
        warnings = service.promotion_warnings(self.roster_a, self.b_player, 1)
        self.assertEqual(len(warnings), 1)
        self.assertIn("moves", warnings[0])
        self.assertFalse(
            service.promotion_warnings(self.roster_a, self.a_player, 1),
            "Players of the team itself never get a warning.",
        )

    def test_other_clubs_and_unranked_teams_are_not_affected(self):
        rival_roster = self.env["federation.team.roster"].create(
            {"team_id": self.rival.id, "season_id": self.season.id}
        )
        self.assertFalse(rival_roster.club_rank_blocked_player_ids)
        self.assertFalse(
            self.env["federation.club.rank.service"].roster_block_reason(
                rival_roster, self.a_player
            )
        )


@tagged("post_install", "-at_install", "sf_club_rank")
class TestSameDivisionFilter(TestClubRank):
    """Players on another club team in the same division are not offered."""

    def _enter(self, team, tournament):
        return self.env["federation.tournament.participant"].create(
            {"tournament_id": tournament.id, "team_id": team.id}
        )

    def test_same_division_players_are_hidden(self):
        self._enter(self.team_a, self.tournament)
        self._enter(self.team_b, self.tournament)
        self.env.invalidate_all()
        self.assertIn(self.b_player, self.roster_a.same_division_player_ids)
        self.assertIn(self.a_player, self.roster_b.same_division_player_ids)
        self.assertNotIn(self.a_player, self.roster_a.same_division_player_ids)

    def test_other_divisions_keep_playing_up(self):
        lower_division = self.env["federation.tournament"].create(
            {
                "name": "Rank Division 2",
                "code": "RKD2",
                "season_id": self.season.id,
                "date_start": "2026-09-01",
            }
        )
        self._enter(self.team_a, self.tournament)
        self._enter(self.team_b, lower_division)
        self.env.invalidate_all()
        self.assertFalse(self.roster_a.same_division_player_ids)
        self.assertFalse(self.roster_b.same_division_player_ids)
