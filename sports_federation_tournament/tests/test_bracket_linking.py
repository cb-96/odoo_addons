from odoo.tests import TransactionCase


class TestBracketLinking(TransactionCase):
    """Tests for bracket wiring and automatic team advancement."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create({
            "name": "Bracket Season",
            "date_start": "2025-09-01",
            "date_end": "2026-06-30",
        })
        cls.club = cls.env["federation.club"].create({"name": "Bracket Club"})
        cls.teams = []
        for i in range(1, 5):
            cls.teams.append(cls.env["federation.team"].create({
                "name": f"BracketTeam{i}",
                "club_id": cls.club.id,
            }))
        cls.tournament = cls.env["federation.tournament"].create({
            "name": "Bracket Tournament",
            "season_id": cls.season.id,
            "date_start": "2025-10-01",
        })
        cls.stage = cls.env["federation.tournament.stage"].create({
            "name": "KO Stage",
            "tournament_id": cls.tournament.id,
            "stage_type": "knockout",
        })
        # Semi-final 1: team[0] vs team[1]
        cls.sf1 = cls.env["federation.match"].create({
            "tournament_id": cls.tournament.id,
            "stage_id": cls.stage.id,
            "home_team_id": cls.teams[0].id,
            "away_team_id": cls.teams[1].id,
            "bracket_position": 1,
        })
        # Semi-final 2: team[2] vs team[3]
        cls.sf2 = cls.env["federation.match"].create({
            "tournament_id": cls.tournament.id,
            "stage_id": cls.stage.id,
            "home_team_id": cls.teams[2].id,
            "away_team_id": cls.teams[3].id,
            "bracket_position": 2,
        })
        # Final: winner of SF1 vs winner of SF2
        cls.final = cls.env["federation.match"].create({
            "tournament_id": cls.tournament.id,
            "stage_id": cls.stage.id,
            "source_match_1_id": cls.sf1.id,
            "source_match_2_id": cls.sf2.id,
            "source_type_1": "winner",
            "source_type_2": "winner",
            "bracket_position": 3,
        })

    def test_source_match_wiring(self):
        self.assertEqual(self.final.source_match_1_id, self.sf1)
        self.assertEqual(self.final.source_match_2_id, self.sf2)

    def test_next_matches_computed(self):
        self.assertIn(self.final, self.sf1.next_match_ids)
        self.assertIn(self.final, self.sf2.next_match_ids)

    def test_advance_bracket_sets_winner_home_team(self):
        """Team 0 beats Team 1 in SF1 → Team 0 should become home team of final."""
        self.sf1.write({"home_score": 2, "away_score": 0, "state": "done"})
        self.sf1._advance_bracket_teams()
        self.assertEqual(self.final.home_team_id, self.teams[0])

    def test_advance_bracket_sets_loser_path(self):
        """If source_type_1='loser', the losing team advances."""
        self.final.source_type_1 = "loser"
        self.sf1.write({"home_score": 2, "away_score": 0, "state": "done"})
        self.sf1._advance_bracket_teams()
        # Loser = away_team (Team 1)
        self.assertEqual(self.final.home_team_id, self.teams[1])

    def test_advance_bracket_does_not_advance_on_draw(self):
        """A draw should not trigger automatic advancement."""
        self.sf2.write({"home_score": 1, "away_score": 1, "state": "done"})
        self.sf2._advance_bracket_teams()
        # No team should be set in final.away_team_id
        self.assertFalse(self.final.away_team_id)
