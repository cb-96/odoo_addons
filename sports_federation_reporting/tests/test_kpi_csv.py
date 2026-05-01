"""
Tests for KPI CSV export controller (Phase 4).

These are ORM-level tests that verify the data layer (queries + serialization)
used by the CSV export endpoints without making real HTTP requests.
Tests cover:
- Standings CSV: correct columns, row count, content per standing line
- Participation CSV: correct columns, row count, correct state encoding
- Missing tournament / season returns empty (graceful handling of empty result sets)
"""

import csv
import io
from odoo.tests.common import TransactionCase


class TestKpiCsvExport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "KPI Club",
                "code": "KPIC",
            }
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "KPI Team A",
                "club_id": cls.club.id,
                "code": "KPITA",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "KPI Team B",
                "club_id": cls.club.id,
                "code": "KPITB",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "KPI Season",
                "code": "KPIS24",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "KPI Tournament",
                "code": "KPIT",
                "season_id": cls.season.id,
                "date_start": "2024-06-01",
            }
        )
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "KPI Rules",
                "code": "KPIRS",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )
        cls.finance_fee_type = cls.env["federation.fee.type"].create(
            {
                "name": "KPI Finance Fee",
                "code": "KPIFIN",
                "category": "registration",
                "default_amount": 75.00,
            }
        )
        cls.participant_a = cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_a.id,
            }
        )
        cls.participant_b = cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_b.id,
            }
        )
        cls.standing = cls.env["federation.standing"].create(
            {
                "name": "KPI Standing",
                "tournament_id": cls.tournament.id,
                "rule_set_id": cls.rule_set.id,
            }
        )
        # Create a match so standings actually compute
        match_vals = {
            "tournament_id": cls.tournament.id,
            "home_team_id": cls.team_a.id,
            "away_team_id": cls.team_b.id,
            "home_score": 2,
            "away_score": 1,
            "state": "done",
        }
        if "include_in_official_standings" in cls.env["federation.match"]._fields:
            match_vals["include_in_official_standings"] = True
        cls.match = cls.env["federation.match"].create(match_vals)
        cls.standing.action_recompute()
        cls.finance_event_draft = cls.env["federation.finance.event"].create(
            {
                "name": "KPI Draft Fee",
                "fee_type_id": cls.finance_fee_type.id,
                "event_type": "charge",
                "amount": 75.00,
                "source_model": "federation.club",
                "source_res_id": cls.club.id,
                "club_id": cls.club.id,
            }
        )
        cls.finance_event_confirmed = cls.env["federation.finance.event"].create(
            {
                "name": "KPI Confirmed Fee",
                "fee_type_id": cls.finance_fee_type.id,
                "event_type": "charge",
                "amount": 90.00,
                "source_model": "federation.team",
                "source_res_id": cls.team_a.id,
                "club_id": cls.club.id,
            }
        )
        cls.finance_event_confirmed.action_confirm()

    # ---------------------------------------------------------------
    # Helper: build CSV from data as the controller would
    # ---------------------------------------------------------------

    def _build_standings_csv(self, tournament_id):
        """Mirror the controller's CSV generation logic."""
        standings = self.env["federation.standing"].search(
            [
                ("tournament_id", "=", tournament_id),
            ],
            order="name asc",
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Standing",
                "Rank",
                "Team",
                "Club",
                "Played",
                "Won",
                "Drawn",
                "Lost",
                "GF",
                "GA",
                "GD",
                "Points",
                "Tiebreak Notes",
            ]
        )
        for standing in standings:
            for line in standing.line_ids.sorted(lambda ln: ln.rank):
                writer.writerow(
                    [
                        standing.name,
                        line.rank,
                        line.team_id.name if line.team_id else "",
                        line.club_id.name if line.club_id else "",
                        line.played,
                        line.won,
                        line.drawn,
                        line.lost,
                        line.score_for,
                        line.score_against,
                        line.score_diff,
                        line.points,
                        line.tiebreak_notes or "",
                    ]
                )
        output.seek(0)
        return list(csv.reader(output))

    def _build_participation_csv(self, season_id):
        """Mirror the controller's participation CSV generation logic."""
        participants = self.env["federation.tournament.participant"].search(
            [
                ("tournament_id.season_id", "=", season_id),
            ],
            order="tournament_id asc, team_id asc",
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Tournament", "Season", "Team", "Club", "State"])
        for p in participants:
            writer.writerow(
                [
                    p.tournament_id.name if p.tournament_id else "",
                    p.tournament_id.season_id.name if p.tournament_id.season_id else "",
                    p.team_id.name if p.team_id else "",
                    p.club_id.name if p.club_id else "",
                    p.state or "",
                ]
            )
        output.seek(0)
        return list(csv.reader(output))

    def _build_finance_csv(self):
        """Mirror the controller's finance CSV generation logic."""
        finance_rows = self.env["federation.report.finance"].search(
            [],
            order="fee_type_id asc, state asc",
        )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "Fee Type",
                "Category",
                "State",
                "Event Count",
                "Total Amount",
            ]
        )
        for row in finance_rows:
            writer.writerow(
                [
                    row.fee_type_id.name if row.fee_type_id else "",
                    row.fee_type_id.category if row.fee_type_id else "",
                    row.state or "",
                    row.event_count,
                    row.total_amount,
                ]
            )
        output.seek(0)
        return list(csv.reader(output))

    # ---------------------------------------------------------------
    # Standings CSV tests
    # ---------------------------------------------------------------

    def test_standings_csv_has_header_row(self):
        """Generated CSV starts with expected column headers."""
        rows = self._build_standings_csv(self.tournament.id)
        self.assertTrue(rows, "CSV should not be empty.")
        header = rows[0]
        self.assertEqual(header[0], "Standing")
        self.assertEqual(header[1], "Rank")
        self.assertEqual(header[2], "Team")
        self.assertIn("Points", header)
        self.assertIn("Tiebreak Notes", header)

    def test_standings_csv_row_count_matches_lines(self):
        """One data row per standing line."""
        rows = self._build_standings_csv(self.tournament.id)
        data_rows = rows[1:]  # skip header
        expected = sum(
            len(s.line_ids)
            for s in self.env["federation.standing"].search(
                [
                    ("tournament_id", "=", self.tournament.id),
                ]
            )
        )
        self.assertEqual(len(data_rows), expected)

    def test_standings_csv_team_names_present(self):
        """Team names appear in the CSV data rows."""
        rows = self._build_standings_csv(self.tournament.id)
        team_names_in_csv = [row[2] for row in rows[1:]]
        self.assertIn(self.team_a.name, team_names_in_csv)
        self.assertIn(self.team_b.name, team_names_in_csv)

    def test_standings_csv_winner_has_3_points(self):
        """Team A won 2-1 so should have 3 points in standings CSV."""
        rows = self._build_standings_csv(self.tournament.id)
        # column index 11 = Points
        points_col = 11
        team_col = 2
        team_a_row = next(
            (r for r in rows[1:] if r[team_col] == self.team_a.name), None
        )
        self.assertIsNotNone(team_a_row, "Team A not found in standings CSV.")
        self.assertEqual(int(team_a_row[points_col]), 3)

    def test_standings_csv_no_tournament_is_empty(self):
        """Standing CSV for non-existent tournament has only the header."""
        rows = self._build_standings_csv(-999)
        self.assertEqual(len(rows), 1, "Only header should be present.")

    # ---------------------------------------------------------------
    # Participation CSV tests
    # ---------------------------------------------------------------

    def test_participation_csv_has_header_row(self):
        """Generated CSV starts with expected headers."""
        rows = self._build_participation_csv(self.season.id)
        self.assertTrue(rows, "CSV should not be empty.")
        header = rows[0]
        self.assertEqual(header[0], "Tournament")
        self.assertIn("State", header)

    def test_participation_csv_row_count_matches_participants(self):
        """One row per participant registered to tournaments in the season."""
        rows = self._build_participation_csv(self.season.id)
        data_rows = rows[1:]
        expected = self.env["federation.tournament.participant"].search_count(
            [
                ("tournament_id.season_id", "=", self.season.id),
            ]
        )
        self.assertEqual(len(data_rows), expected)

    def test_participation_csv_includes_both_teams(self):
        """Both Team A and Team B appear in the participation CSV."""
        rows = self._build_participation_csv(self.season.id)
        team_names = [r[2] for r in rows[1:]]
        self.assertIn(self.team_a.name, team_names)
        self.assertIn(self.team_b.name, team_names)

    def test_participation_csv_state_column(self):
        """State column reflects actual participant state."""
        rows = self._build_participation_csv(self.season.id)
        states_in_csv = [r[4] for r in rows[1:]]
        for state in states_in_csv:
            self.assertTrue(state, "State should not be empty.")

    def test_participation_csv_no_season_is_empty(self):
        """Participation CSV for non-existent season has only the header."""
        rows = self._build_participation_csv(-999)
        self.assertEqual(len(rows), 1)

    # ---------------------------------------------------------------
    # Finance CSV tests
    # ---------------------------------------------------------------

    def test_finance_csv_has_header_row(self):
        """Generated finance CSV starts with the expected headers."""
        rows = self._build_finance_csv()
        self.assertTrue(rows, "CSV should not be empty.")
        self.assertEqual(
            rows[0],
            ["Fee Type", "Category", "State", "Event Count", "Total Amount"],
        )

    def test_finance_csv_includes_confirmed_and_draft_rows(self):
        """Finance CSV contains grouped rows for the finance report states present."""
        rows = self._build_finance_csv()
        states = [row[2] for row in rows[1:] if row[0] == self.finance_fee_type.name]
        self.assertIn("draft", states)
        self.assertIn("confirmed", states)

    def test_finance_csv_aggregates_amounts(self):
        """Finance CSV exposes aggregated totals from the report model."""
        rows = self._build_finance_csv()
        draft_row = next(
            (
                row
                for row in rows[1:]
                if row[0] == self.finance_fee_type.name and row[2] == "draft"
            ),
            None,
        )
        confirmed_row = next(
            (
                row
                for row in rows[1:]
                if row[0] == self.finance_fee_type.name and row[2] == "confirmed"
            ),
            None,
        )
        self.assertIsNotNone(draft_row)
        self.assertIsNotNone(confirmed_row)
        self.assertEqual(float(draft_row[4]), 75.0)
        self.assertEqual(float(confirmed_row[4]), 90.0)
