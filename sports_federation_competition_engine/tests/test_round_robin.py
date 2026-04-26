from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
from datetime import datetime


class TestRoundRobin(TransactionCase):
    """Tests for round-robin schedule generation."""

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        # Create a club and teams
        cls.club = cls.env["federation.club"].create({"name": "Test Club"})
        cls.teams = cls.env["federation.team"]
        for i in range(1, 7):
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
                "name": "Group Stage",
                "tournament_id": cls.tournament.id,
                "stage_type": "group",
            }
        )
        # Create participants
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

    def _generate(self, double_round=False, overwrite=False):
        """Helper to generate round-robin."""
        options = {
            "double_round": double_round,
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": overwrite,
            "group": False,
        }
        engine = self.env["federation.competition.engine.service"]
        return engine.generate_round_robin_schedule(
            self.tournament, self.stage, self.participants, options
        )

    def test_even_participant_count(self):
        """6 teams: 5 rounds * 3 matches = 15 matches."""
        matches = self._generate()
        self.assertEqual(len(matches), 15)

    def test_odd_participant_count(self):
        """5 teams: 5 rounds * 2 matches = 10 matches (one team has bye each round)."""
        odd_participants = self.participants[:5]
        options = {
            "double_round": False,
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": False,
            "group": False,
        }
        engine = self.env["federation.competition.engine.service"]
        matches = engine.generate_round_robin_schedule(
            self.tournament, self.stage, odd_participants, options
        )
        # 5 teams -> 5 rounds, 2 matches per round = 10 matches
        self.assertEqual(len(matches), 10)

    def test_no_self_pairings(self):
        """Ensure no team plays itself."""
        matches = self._generate()
        for match in matches:
            self.assertNotEqual(
                match.home_team_id,
                match.away_team_id,
                f"Team {match.home_team_id.name} should not play itself",
            )

    def test_double_round(self):
        """Double round should produce twice the matches."""
        single = self._generate(double_round=False)
        # Clear matches
        self.env["federation.match"].browse([m.id for m in single]).unlink()
        double = self._generate(double_round=True, overwrite=True)
        self.assertEqual(len(double), 30)  # 15 * 2

    def test_overwrite_protection(self):
        """Cannot regenerate without overwrite enabled."""
        self._generate()
        with self.assertRaises(UserError):
            self._generate(overwrite=False)

    def test_overwrite_allowed(self):
        """Can regenerate with overwrite enabled."""
        first = self._generate()
        self.assertEqual(len(first), 15)
        second = self._generate(overwrite=True)
        self.assertEqual(len(second), 15)

    def test_tournament_state_validation(self):
        """Cannot generate for draft tournament."""
        self.tournament.state = "draft"
        with self.assertRaises(UserError):
            self._generate()

    def test_minimum_participants(self):
        """Need at least 2 participants."""
        with self.assertRaises(UserError):
            options = {
                "double_round": False,
                "start_datetime": False,
                "interval_hours": 0,
                "venue": "",
                "overwrite": False,
                "group": False,
            }
            engine = self.env["federation.competition.engine.service"]
            engine.generate_round_robin_schedule(
                self.tournament, self.stage, self.participants[:1], options
            )

    def test_each_team_plays_all_others_once(self):
        """Verify each team plays every other team exactly once (single round)."""
        matches = self._generate(double_round=False)
        team_ids = self.teams.ids
        for team_id in team_ids:
            opponents = []
            for match in matches:
                if match.home_team_id.id == team_id:
                    opponents.append(match.away_team_id.id)
                elif match.away_team_id.id == team_id:
                    opponents.append(match.home_team_id.id)
            # Each team should play 5 opponents (6 teams total)
            self.assertEqual(
                len(opponents), 5, f"Team {team_id} should play 5 opponents"
            )
            # No duplicates
            self.assertEqual(
                len(set(opponents)), 5, f"Team {team_id} should not have duplicate opponents"
            )

    def test_deterministic_ordering(self):
        """Same input should produce same pairings."""
        first = self._generate()
        first_pairs = {(m.home_team_id.id, m.away_team_id.id) for m in first}
        self.env["federation.match"].browse([m.id for m in first]).unlink()
        second = self._generate(overwrite=True)
        # Compare team pairings (order of matches may vary but pairings should be same)
        second_pairs = {(m.home_team_id.id, m.away_team_id.id) for m in second}
        self.assertEqual(first_pairs, second_pairs)

    def test_round_numbers_follow_generated_rounds(self):
        """Generated matches should persist round numbers for downstream scheduling tools."""
        matches = self.env["federation.match"].browse([match.id for match in self._generate(double_round=False)])

        round_numbers = sorted(set(matches.mapped("round_number")))
        self.assertEqual(round_numbers, [1, 2, 3, 4, 5])

    def test_existing_round_mode_uses_only_existing(self):
        """Round mode 'existing' should spread matches across existing rounds."""
        # Create 3 pre-existing rounds
        for i in range(1, 4):
            self.env["federation.tournament.round"].create({
                "stage_id": self.stage.id,
                "sequence": i,
                "name": f"Round {i}",
            })

        options = {
            "double_round": False,
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": False,
            "group": False,
            "round_mode": "existing",
            "requested_rounds": 0,
        }
        engine = self.env["federation.competition.engine.service"]
        # 6 teams need 5 rounds, but with 3 existing rounds it should spread matches across them
        matches = engine.generate_round_robin_schedule(
            self.tournament, self.stage, self.participants, options
        )
        # Should still create 15 matches, distributed across 3 rounds
        self.assertEqual(len(matches), 15)

    def test_existing_round_mode_spreads_across_fewer_rounds(self):
        """Round mode 'existing' should spread matches across fewer existing rounds."""
        # Create 2 pre-existing rounds (fewer than the 5 needed mathematically)
        for i in range(1, 3):
            self.env["federation.tournament.round"].create({
                "stage_id": self.stage.id,
                "sequence": i,
                "name": f"Round {i}",
            })

        options = {
            "double_round": False,
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": False,
            "group": False,
            "round_mode": "existing",
            "requested_rounds": 0,
        }
        engine = self.env["federation.competition.engine.service"]
        matches = engine.generate_round_robin_schedule(
            self.tournament, self.stage, self.participants, options
        )
        # Should still create 15 matches, distributed across 2 rounds
        self.assertEqual(len(matches), 15)

    def test_explicit_round_mode_creates_specific_count(self):
        """Round mode 'explicit' should create specific number of rounds."""
        options = {
            "double_round": False,
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": False,
            "group": False,
            "round_mode": "explicit",
            "requested_rounds": 10,  # More than needed
        }
        engine = self.env["federation.competition.engine.service"]
        matches = engine.generate_round_robin_schedule(
            self.tournament, self.stage, self.participants, options
        )
        # Should create 10 rounds but only use 5 for 15 matches
        self.assertEqual(len(matches), 15)
        # Verify 10 rounds were created
        rounds = self.env["federation.tournament.round"].search([
            ("stage_id", "=", self.stage.id)
        ])
        self.assertEqual(len(rounds), 10)

    def test_explicit_round_mode_insufficient_rounds(self):
        """Round mode 'explicit' should fail if requested rounds less than needed."""
        options = {
            "double_round": False,
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": False,
            "group": False,
            "round_mode": "explicit",
            "requested_rounds": 3,  # Less than needed (5)
        }
        engine = self.env["federation.competition.engine.service"]
        with self.assertRaises(UserError):
            engine.generate_round_robin_schedule(
                self.tournament, self.stage, self.participants, options
            )

        for round_number in round_numbers:
            round_matches = matches.filtered(lambda match: match.round_number == round_number)
            self.assertEqual(len(round_matches), 3)
            self.assertEqual(len(round_matches.mapped("round_id")), 1)
            self.assertEqual(round_matches.mapped("round_id.sequence"), [round_number])