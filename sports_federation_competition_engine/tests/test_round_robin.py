from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
from datetime import datetime  # noqa: F401


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

        # Create 5 pre-defined gamedays (single RR for 6 teams needs exactly 5)
        cls.rounds = cls.env["federation.tournament.round"]
        for i in range(1, 6):
            cls.rounds |= cls.env["federation.tournament.round"].create(
                {
                    "stage_id": cls.stage.id,
                    "sequence": i,
                    "name": f"Gameday {i}",
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
        # Double round for 6 teams needs 10 algorithm rounds; use a dedicated stage
        # with 10 gamedays so each leg stays in its own gameday (no duplicate-pairing
        # constraint violation).
        stage_dbl = self.env["federation.tournament.stage"].create(
            {
                "name": "Double Stage",
                "tournament_id": self.tournament.id,
                "stage_type": "group",
            }
        )
        for i in range(1, 11):
            self.env["federation.tournament.round"].create(
                {
                    "stage_id": stage_dbl.id,
                    "sequence": i,
                    "name": f"Gameday {i}",
                }
            )
        options = {
            "double_round": True,
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": False,
            "group": False,
        }
        engine = self.env["federation.competition.engine.service"]
        double = engine.generate_round_robin_schedule(
            self.tournament, stage_dbl, self.participants, options
        )
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
                len(set(opponents)),
                5,
                f"Team {team_id} should not have duplicate opponents",
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
        matches = self.env["federation.match"].browse(
            [match.id for match in self._generate(double_round=False)]
        )

        round_numbers = sorted(set(matches.mapped("round_number")))
        self.assertEqual(round_numbers, [1, 2, 3, 4, 5])

    def test_existing_round_mode_uses_only_existing(self):
        """Matches are distributed across all pre-defined gamedays."""
        matches = self._generate()
        self.assertEqual(len(matches), 15)
        round_ids = {m.round_id.id for m in matches}
        # All 5 pre-defined gamedays receive matches (5 algorithm rounds → 5 gamedays)
        self.assertEqual(len(round_ids), 5)

    def test_existing_round_mode_spreads_across_fewer_rounds(self):
        """When fewer gamedays than algorithm rounds, matches cycle across available gamedays."""
        stage2 = self.env["federation.tournament.stage"].create(
            {
                "name": "Stage 2",
                "tournament_id": self.tournament.id,
                "stage_type": "group",
            }
        )
        for i in range(1, 3):
            self.env["federation.tournament.round"].create(
                {
                    "stage_id": stage2.id,
                    "sequence": i,
                    "name": f"Gameday {i}",
                }
            )
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
            self.tournament, stage2, self.participants, options
        )
        self.assertEqual(len(matches), 15)
        round_ids = {m.round_id.id for m in matches}
        # Only 2 gamedays exist — cycling distributes all matches across them
        self.assertEqual(len(round_ids), 2)

    def test_no_gamedays_raises_user_error(self):
        """UserError is raised when no gamedays exist for the stage."""
        from odoo.exceptions import UserError

        stage3 = self.env["federation.tournament.stage"].create(
            {
                "name": "Stage 3",
                "tournament_id": self.tournament.id,
                "stage_type": "group",
            }
        )
        options = {
            "double_round": False,
            "start_datetime": False,
            "interval_hours": 0,
            "venue": "",
            "overwrite": False,
            "group": False,
        }
        engine = self.env["federation.competition.engine.service"]
        with self.assertRaises(UserError):
            engine.generate_round_robin_schedule(
                self.tournament, stage3, self.participants, options
            )
