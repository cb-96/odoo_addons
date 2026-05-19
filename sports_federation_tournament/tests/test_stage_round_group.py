from datetime import date

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestFederationTournamentStage(TransactionCase):
    """Tests for federation.tournament.stage."""

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
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Test Tournament",
                "season_id": cls.season.id,
                "date_start": "2025-09-01",
            }
        )

    def _make_stage(self, **kwargs):
        vals = {
            "name": "Stage",
            "tournament_id": self.tournament.id,
            "stage_type": "group",
        }
        vals.update(kwargs)
        return self.env["federation.tournament.stage"].create(vals)

    def test_create_stage(self):
        stage = self._make_stage(name="Group Phase")
        self.assertEqual(stage.name, "Group Phase")
        self.assertEqual(stage.tournament_id, self.tournament)
        self.assertEqual(stage.stage_type, "group")

    def test_date_validation_end_before_start_raises(self):
        with self.assertRaises(ValidationError):
            self._make_stage(
                date_start=date(2025, 10, 10),
                date_end=date(2025, 10, 5),
            )

    def test_date_validation_same_day_allowed(self):
        stage = self._make_stage(
            date_start=date(2025, 10, 5),
            date_end=date(2025, 10, 5),
        )
        self.assertEqual(stage.date_start, date(2025, 10, 5))

    def test_computed_counts_start_at_zero(self):
        stage = self._make_stage()
        self.assertEqual(stage.group_count, 0)
        self.assertEqual(stage.round_count, 0)
        self.assertEqual(stage.match_count, 0)

    def test_round_count_increments(self):
        stage = self._make_stage()
        self.assertEqual(stage.round_count, 0)
        self.env["federation.tournament.round"].create(
            {
                "stage_id": stage.id,
                "sequence": 1,
            }
        )
        self.assertEqual(stage.round_count, 1)

    def test_stage_types(self):
        for stype in ("group", "knockout", "final", "placement"):
            stage = self._make_stage(stage_type=stype)
            self.assertEqual(stage.stage_type, stype)


class TestFederationTournamentRound(TransactionCase):
    """Tests for federation.tournament.round."""

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
            }
        )
        cls.club = cls.env["federation.club"].create({"name": "Club"})
        cls.team_a = cls.env["federation.team"].create(
            {"name": "Team A", "club_id": cls.club.id}
        )
        cls.team_b = cls.env["federation.team"].create(
            {"name": "Team B", "club_id": cls.club.id}
        )

    def _make_round(self, **kwargs):
        vals = {"stage_id": self.stage.id, "sequence": 1}
        vals.update(kwargs)
        return self.env["federation.tournament.round"].create(vals)

    def test_auto_name_from_stage(self):
        rnd = self._make_round(sequence=2)
        self.assertIn("Group Stage", rnd.name)
        self.assertIn("2", rnd.name)

    def test_explicit_name_preserved(self):
        rnd = self._make_round(name="Matchday 1")
        self.assertEqual(rnd.name, "Matchday 1")

    def test_auto_name_with_group(self):
        group = self.env["federation.tournament.group"].create(
            {
                "name": "Group A",
                "stage_id": self.stage.id,
            }
        )
        rnd = self._make_round(group_id=group.id, sequence=1)
        self.assertIn("Group A", rnd.name)

    def test_sequence_unique_within_stage_group_scope(self):
        self._make_round(sequence=5)
        with self.assertRaises(ValidationError):
            self._make_round(sequence=5)

    def test_sequence_must_be_positive(self):
        with self.assertRaises(ValidationError):
            self._make_round(sequence=0)

    def test_match_count_computed(self):
        rnd = self._make_round(sequence=3)
        self.assertEqual(rnd.match_count, 0)
        self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.stage.id,
                "round_id": rnd.id,
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
            }
        )
        self.assertEqual(rnd.match_count, 1)

    def test_round_date_change_syncs_match_date(self):
        rnd = self._make_round(
            round_date=date(2025, 10, 5),
            sequence=4,
        )
        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.stage.id,
                "round_id": rnd.id,
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
                "scheduled_time": 15.0,
            }
        )
        self.assertEqual(match.date_scheduled.date(), date(2025, 10, 5))

        rnd.write({"round_date": date(2025, 10, 19)})
        self.assertEqual(match.date_scheduled.date(), date(2025, 10, 19))

    def test_round_tournament_related_to_stage(self):
        rnd = self._make_round(sequence=6)
        self.assertEqual(rnd.tournament_id, self.tournament)


class TestFederationTournamentGroup(TransactionCase):
    """Tests for federation.tournament.group."""

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
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Test Tournament",
                "season_id": cls.season.id,
                "date_start": "2025-09-01",
            }
        )
        cls.stage = cls.env["federation.tournament.stage"].create(
            {
                "name": "Group Phase",
                "tournament_id": cls.tournament.id,
            }
        )

    def test_create_group(self):
        group = self.env["federation.tournament.group"].create(
            {
                "name": "Group A",
                "stage_id": self.stage.id,
            }
        )
        self.assertEqual(group.name, "Group A")
        self.assertEqual(group.stage_id, self.stage)

    def test_group_stage_count_updates(self):
        self.assertEqual(self.stage.group_count, 0)
        self.env["federation.tournament.group"].create(
            {
                "name": "Group B",
                "stage_id": self.stage.id,
            }
        )
        self.assertEqual(self.stage.group_count, 1)
