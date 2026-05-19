from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestKnockout(TransactionCase):
    """Tests for knockout bracket generation."""

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        # Create a club and teams
        cls.club = cls.env["federation.club"].create({"name": "Test Club"})
        cls.teams = cls.env["federation.team"]
        for i in range(1, 9):
            cls.teams |= cls.env["federation.team"].create(
                {"name": f"Team {i}", "club_id": cls.club.id}
            )
        # Create a season
        cls.season = cls.env["federation.season"].create(
            {"name": "2025-2026", "date_start": "2025-09-01", "date_end": "2026-06-30"}
        )
        # Create a tournament
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Test Tournament",
                "date_start": "2025-10-01",
                "season_id": cls.season.id,
                "state": "open",
            }
        )
        # Create a stage
        cls.stage = cls.env["federation.tournament.stage"].create(
            {
                "name": "Knockout",
                "tournament_id": cls.tournament.id,
                "stage_type": "knockout",
            }
        )
        # Create participants with seeds
        cls.participants = cls.env["federation.tournament.participant"]
        for idx, team in enumerate(cls.teams, start=1):
            cls.participants |= cls.env["federation.tournament.participant"].create(
                {
                    "tournament_id": cls.tournament.id,
                    "team_id": team.id,
                    "state": "confirmed",
                    "seed": idx,
                }
            )

    def _generate(
        self, seeding="seed", bracket_size="natural", overwrite=False, seed=None
    ):
        """Helper to generate knockout bracket."""
        options = {
            "seeding": seeding,
            "bracket_size": bracket_size,
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": overwrite,
        }
        if seed is not None:
            options["seed"] = seed
        engine = self.env["federation.competition.engine.service"]
        return engine.generate_knockout_bracket(
            self.tournament, self.stage, self.participants, options
        )

    def test_eight_teams_natural(self):
        """8 teams natural bracket: full bracket 4+2+1 = 7 matches."""
        matches = self._generate(bracket_size="natural")
        self.assertEqual(len(matches), 7)

    def test_eight_teams_power_of_two(self):
        """8 teams power of 2: full bracket 4+2+1 = 7 matches."""
        matches = self._generate(bracket_size="power_of_two")
        self.assertEqual(len(matches), 7)

    def test_six_teams_power_of_two(self):
        """6 teams, power-of-two bracket builds the full seeded bracket."""
        six_participants = self.participants[:6]
        options = {
            "seeding": "seed",
            "bracket_size": "power_of_two",
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": False,
        }
        engine = self.env["federation.competition.engine.service"]
        matches = engine.generate_knockout_bracket(
            self.tournament, self.stage, six_participants, options
        )
        self.assertEqual(len(matches), 5)

        first_round = [m for m in matches if m.round_number == 1]
        second_round = [m for m in matches if m.round_number == 2]
        final_round = [m for m in matches if m.round_number == 3]

        self.assertEqual(len(first_round), 2)
        self.assertEqual(len(second_round), 2)
        self.assertEqual(len(final_round), 1)

    def test_three_teams_power_of_two(self):
        """3 teams, power-of-two bracket creates a play-in plus final."""
        three_participants = self.participants[:3]
        options = {
            "seeding": "seed",
            "bracket_size": "power_of_two",
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": False,
        }
        engine = self.env["federation.competition.engine.service"]
        matches = engine.generate_knockout_bracket(
            self.tournament, self.stage, three_participants, options
        )
        self.assertEqual(len(matches), 2)

        first_round = [m for m in matches if m.round_number == 1]
        final_round = [m for m in matches if m.round_number == 2]

        self.assertEqual(len(first_round), 1)
        self.assertEqual(len(final_round), 1)

    def test_seeding_correctness(self):
        """Top seed should play bottom seed in first round."""
        matches = self._generate(seeding="seed", bracket_size="natural")
        # 8 teams: seed 1 vs seed 8, seed 2 vs seed 7, etc.
        match_list = [(m.home_team_id.name, m.away_team_id.name) for m in matches]
        # Seed 1 (Team 1) should play Seed 8 (Team 8)
        self.assertIn(("Team 1", "Team 8"), match_list)
        # Seed 2 (Team 2) should play Seed 7 (Team 7)
        self.assertIn(("Team 2", "Team 7"), match_list)

    def test_no_self_pairings(self):
        """Ensure no team plays itself (in first round matches only)."""
        matches = self._generate()
        first_round = [m for m in matches if m.home_team_id and m.away_team_id]
        for match in first_round:
            self.assertNotEqual(
                match.home_team_id,
                match.away_team_id,
                f"Team {match.home_team_id.name} should not play itself",
            )

    def test_overwrite_protection(self):
        """Cannot regenerate without overwrite enabled."""
        self._generate()
        with self.assertRaises(UserError):
            self._generate(overwrite=False)

    def test_overwrite_allowed(self):
        """Can regenerate with overwrite enabled."""
        first = self._generate()
        self.assertEqual(len(first), 7)
        second = self._generate(overwrite=True)
        self.assertEqual(len(second), 7)

    def test_knockout_wizard_overwrite_warning_uses_alert_role(self):
        """The overwrite warning should keep the Odoo alert accessibility role."""
        view = self.env.ref(
            "sports_federation_competition_engine.view_knockout_wizard_form"
        )

        self.assertIn('class="alert alert-warning"', view.arch_db)
        self.assertIn('role="alert"', view.arch_db)

    def test_tournament_state_validation(self):
        """Cannot generate for draft tournament."""
        self.tournament.state = "draft"
        with self.assertRaises(UserError):
            self._generate()

    def test_minimum_participants(self):
        """Need at least 2 participants."""
        with self.assertRaises(UserError):
            options = {
                "seeding": "seed",
                "bracket_size": "natural",
                "start_datetime": False,
                "interval_hours": 0,
                "venue": "",
                "overwrite": False,
            }
            engine = self.env["federation.competition.engine.service"]
            engine.generate_knockout_bracket(
                self.tournament, self.stage, self.participants[:1], options
            )

    def test_bye_seeding_top_seeds(self):
        """With byes, top seeds skip the play-in round."""
        six_participants = self.participants[:6]
        options = {
            "seeding": "seed",
            "bracket_size": "power_of_two",
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": False,
        }
        engine = self.env["federation.competition.engine.service"]
        matches = engine.generate_knockout_bracket(
            self.tournament, self.stage, six_participants, options
        )
        first_round = [m for m in matches if m.round_number == 1]
        playing_teams = set()
        for m in first_round:
            playing_teams.add(m.home_team_id.id)
            playing_teams.add(m.away_team_id.id)
        self.assertNotIn(self.teams[0].id, playing_teams)
        self.assertNotIn(self.teams[1].id, playing_teams)

    def test_bye_sources_fill_second_round_placeholders(self):
        """Top seeds should be wired directly into the second round."""
        six_participants = self.participants[:6]
        options = {
            "seeding": "seed",
            "bracket_size": "power_of_two",
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": False,
        }
        engine = self.env["federation.competition.engine.service"]
        matches = engine.generate_knockout_bracket(
            self.tournament, self.stage, six_participants, options
        )

        first_round = sorted(
            [m for m in matches if m.round_number == 1],
            key=lambda match: match.bracket_position,
        )
        second_round = sorted(
            [m for m in matches if m.round_number == 2],
            key=lambda match: match.bracket_position,
        )

        self.assertEqual(second_round[0].home_team_id, self.teams[0])
        self.assertEqual(second_round[0].source_match_2_id, first_round[0])
        self.assertEqual(second_round[1].home_team_id, self.teams[1])
        self.assertEqual(second_round[1].source_match_2_id, first_round[1])

    def test_play_in_winners_auto_advance_into_seeded_slots(self):
        """Completing play-in matches should populate the seeded semifinal slots."""
        six_participants = self.participants[:6]
        options = {
            "seeding": "seed",
            "bracket_size": "power_of_two",
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": False,
        }
        engine = self.env["federation.competition.engine.service"]
        matches = engine.generate_knockout_bracket(
            self.tournament, self.stage, six_participants, options
        )

        first_round = sorted(
            [m for m in matches if m.round_number == 1],
            key=lambda match: match.bracket_position,
        )
        second_round = sorted(
            [m for m in matches if m.round_number == 2],
            key=lambda match: match.bracket_position,
        )

        first_round[0].write({"home_score": 2, "away_score": 1})
        first_round[0].action_done()
        first_round[1].write({"home_score": 0, "away_score": 3})
        first_round[1].action_done()

        self.assertEqual(second_round[0].away_team_id, self.teams[2])
        self.assertEqual(second_round[1].away_team_id, self.teams[4])

    def test_manual_seeding_order(self):
        """Manual seeding should preserve participant order."""
        # Reverse the order manually
        reversed_participants = self.participants[::-1]
        options = {
            "seeding": "manual",
            "bracket_size": "natural",
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": False,
        }
        engine = self.env["federation.competition.engine.service"]
        matches = engine.generate_knockout_bracket(
            self.tournament, self.stage, reversed_participants, options
        )
        # First in list (Team 8) should play last (Team 1)
        match_list = [(m.home_team_id.name, m.away_team_id.name) for m in matches]
        self.assertIn(("Team 8", "Team 1"), match_list)

    def test_random_seeding_deterministic_with_seed(self):
        """Random seeding with a fixed seed produces identical bracket assignments."""
        matches_a = self._generate(seeding="random", seed=42)
        teams_a = [
            (m.home_team_id.id, m.away_team_id.id)
            for m in matches_a
            if not m.source_match_1_id
        ]
        matches_b = self._generate(seeding="random", seed=42, overwrite=True)
        teams_b = [
            (m.home_team_id.id, m.away_team_id.id)
            for m in matches_b
            if not m.source_match_1_id
        ]
        self.assertEqual(
            teams_a, teams_b, "Same seed must yield identical bracket slot assignments"
        )
