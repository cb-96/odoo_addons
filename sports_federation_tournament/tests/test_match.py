from datetime import date

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestFederationMatch(TransactionCase):
    """Tests for federation.match model behaviour."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "2025-2026",
                "date_start": "2025-09-01",
                "date_end": "2026-06-30",
            }
        )
        cls.club = cls.env["federation.club"].create({"name": "Test Club"})
        cls.team_home = cls.env["federation.team"].create(
            {
                "name": "Home FC",
                "club_id": cls.club.id,
            }
        )
        cls.team_away = cls.env["federation.team"].create(
            {
                "name": "Away FC",
                "club_id": cls.club.id,
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Test Tournament",
                "season_id": cls.season.id,
                "date_start": "2025-09-01",
            }
        )
        cls.stage = cls.env["federation.tournament.stage"].create(
            {
                "name": "Group Stage",
                "tournament_id": cls.tournament.id,
                "stage_type": "group",
            }
        )

    def _make_match(self, **kwargs):
        vals = {
            "tournament_id": self.tournament.id,
            "home_team_id": self.team_home.id,
            "away_team_id": self.team_away.id,
        }
        vals.update(kwargs)
        return self.env["federation.match"].create(vals)

    # ── naming ──────────────────────────────────────────────────────────────

    def test_name_computed_from_teams(self):
        match = self._make_match()
        self.assertEqual(match.name, "Home FC vs Away FC")

    def test_name_fallback_without_teams(self):
        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
            }
        )
        self.assertEqual(match.name, "Match")

    # ── validation ──────────────────────────────────────────────────────────

    def test_same_team_home_and_away_raises(self):
        with self.assertRaises(ValidationError):
            self._make_match(
                home_team_id=self.team_home.id,
                away_team_id=self.team_home.id,
            )

    # ── state transitions ───────────────────────────────────────────────────

    def test_state_transitions_full_cycle(self):
        match = self._make_match()
        self.assertEqual(match.state, "draft")

        match.action_schedule()
        self.assertEqual(match.state, "scheduled")

        match.action_start()
        self.assertEqual(match.state, "in_progress")

        match.home_score = 2
        match.away_score = 1
        match.action_done()
        self.assertEqual(match.state, "done")

    def test_action_cancel_from_draft(self):
        match = self._make_match()
        match.action_cancel()
        self.assertEqual(match.state, "cancelled")

    def test_action_draft_resets_state(self):
        match = self._make_match()
        match.action_schedule()
        match.action_draft()
        self.assertEqual(match.state, "draft")

    # ── result helper ────────────────────────────────────────────────────────

    def test_get_result_team_winner(self):
        match = self._make_match()
        match.home_score = 3
        match.away_score = 1
        match.action_done()
        self.assertEqual(match._get_result_team("winner"), self.team_home)
        self.assertEqual(match._get_result_team("loser"), self.team_away)

    def test_get_result_team_away_wins(self):
        match = self._make_match()
        match.home_score = 0
        match.away_score = 2
        match.action_done()
        self.assertEqual(match._get_result_team("winner"), self.team_away)
        self.assertEqual(match._get_result_team("loser"), self.team_home)

    def test_get_result_team_draw_returns_false(self):
        match = self._make_match()
        match.home_score = 1
        match.away_score = 1
        match.action_done()
        self.assertFalse(match._get_result_team("winner"))
        self.assertFalse(match._get_result_team("loser"))

    def test_get_result_team_not_done_returns_false(self):
        match = self._make_match()
        self.assertFalse(match._get_result_team("winner"))

    # ── bracket advancement ──────────────────────────────────────────────────

    def test_bracket_advancement_winner_to_next_home(self):
        """Winner of match1 becomes home_team_id of the next match."""
        match1 = self._make_match()
        match2 = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "source_match_1_id": match1.id,
                "source_type_1": "winner",
            }
        )
        match1.home_score = 2
        match1.away_score = 0
        match1.action_done()
        self.assertEqual(match2.home_team_id, self.team_home)

    def test_bracket_advancement_loser_to_next_away(self):
        """Loser of match1 becomes away_team_id of the next match (source_match_2)."""
        match1 = self._make_match()
        match2 = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "source_match_2_id": match1.id,
                "source_type_2": "loser",
            }
        )
        match1.home_score = 3
        match1.away_score = 1
        match1.action_done()
        self.assertEqual(match2.away_team_id, self.team_away)

    def test_bracket_advancement_draw_does_not_populate_next(self):
        """A draw leaves the next match teams unset."""
        match1 = self._make_match()
        match2 = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "source_match_1_id": match1.id,
            }
        )
        match1.home_score = 1
        match1.away_score = 1
        match1.action_done()
        self.assertFalse(match2.home_team_id)

    # ── schedule normalisation ───────────────────────────────────────────────

    def test_schedule_normalisation_round_date_plus_time(self):
        """Creating a match with a round_id combines round_date + scheduled_time."""
        rnd = self.env["federation.tournament.round"].create(
            {
                "stage_id": self.stage.id,
                "round_date": date(2025, 10, 5),
                "sequence": 1,
            }
        )
        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.stage.id,
                "round_id": rnd.id,
                "home_team_id": self.team_home.id,
                "away_team_id": self.team_away.id,
                "scheduled_time": 15.5,  # 15:30
            }
        )
        self.assertEqual(match.date_scheduled.date(), date(2025, 10, 5))
        self.assertEqual(match.date_scheduled.hour, 15)
        self.assertEqual(match.date_scheduled.minute, 30)

    def test_round_date_change_syncs_to_match(self):
        """Changing round_date updates date_scheduled for matches with a scheduled_time."""
        rnd = self.env["federation.tournament.round"].create(
            {
                "stage_id": self.stage.id,
                "round_date": date(2025, 10, 5),
                "sequence": 1,
            }
        )
        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.stage.id,
                "round_id": rnd.id,
                "home_team_id": self.team_home.id,
                "away_team_id": self.team_away.id,
                "scheduled_time": 14.0,  # 14:00
            }
        )
        self.assertEqual(match.date_scheduled.date(), date(2025, 10, 5))

        rnd.write({"round_date": date(2025, 10, 12)})
        self.assertEqual(match.date_scheduled.date(), date(2025, 10, 12))

    # ── round scope constraint ───────────────────────────────────────────────

    def test_round_scope_wrong_tournament_raises(self):
        """A round from a different tournament cannot be assigned to a match."""
        other_tournament = self.env["federation.tournament"].create(
            {
                "name": "Other Tournament",
                "season_id": self.season.id,
                "date_start": "2025-09-01",
            }
        )
        other_stage = self.env["federation.tournament.stage"].create(
            {
                "name": "Other Stage",
                "tournament_id": other_tournament.id,
            }
        )
        foreign_round = self.env["federation.tournament.round"].create(
            {
                "stage_id": other_stage.id,
                "sequence": 1,
            }
        )
        with self.assertRaises(ValidationError):
            self.env["federation.match"].create(
                {
                    "tournament_id": self.tournament.id,
                    "round_id": foreign_round.id,
                }
            )

    def test_round_defaults_fill_tournament_stage(self):
        """Creating a match with round_id auto-fills tournament_id and stage_id."""
        rnd = self.env["federation.tournament.round"].create(
            {
                "stage_id": self.stage.id,
                "sequence": 1,
            }
        )
        match = self.env["federation.match"].create(
            {
                "round_id": rnd.id,
            }
        )
        self.assertEqual(match.tournament_id, self.tournament)
        self.assertEqual(match.stage_id, self.stage)
