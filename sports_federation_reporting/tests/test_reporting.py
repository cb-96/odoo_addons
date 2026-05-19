from odoo.tests import TransactionCase


class TestReporting(TransactionCase):
    """Smoke tests for the four remaining SQL view models not covered by
    test_operational_reporting.py — verifies column presence and basic
    aggregate logic with seed data."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Test Club",
                "code": "TC001",
                "active": True,
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Test Season",
                "code": "TS2024",
                "date_start": "2024-09-01",
                "date_end": "2025-06-30",
                "active": True,
            }
        )
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Test Team",
                "code": "TT001",
                "club_id": cls.club.id,
            }
        )
        cls.player = cls.env["federation.player"].create(
            {
                "first_name": "Alice",
                "last_name": "Tester",
                "club_id": cls.club.id,
                "gender": "female",
            }
        )
        cls.referee = cls.env["federation.referee"].create(
            {
                "name": "Test Referee",
                "email": "referee@example.com",
                "active": True,
            }
        )
        cls.fee_type = cls.env["federation.fee.type"].create(
            {
                "name": "Test Fee",
                "code": "TESTFEE",
                "category": "registration",
                "default_amount": 100.00,
            }
        )
        cls.finance_event = cls.env["federation.finance.event"].create(
            {
                "name": "Test Finance Event",
                "fee_type_id": cls.fee_type.id,
                "event_type": "charge",
                "amount": 100.00,
                "state": "draft",
                "source_model": "federation.club",
                "source_res_id": cls.club.id,
                "club_id": cls.club.id,
            }
        )
        cls.requirement = cls.env["federation.document.requirement"].create(
            {
                "name": "Test Insurance",
                "code": "TESTINS",
                "target_model": "federation.club",
                "required_for_all": True,
            }
        )
        cls.compliance_check = cls.env["federation.compliance.check"].create(
            {
                "name": "Test Club Insurance",
                "target_model": "federation.club",
                "club_id": cls.club.id,
                "status": "missing",
                "requirement_id": cls.requirement.id,
            }
        )

    # ------------------------------------------------------------------
    # federation.report.participation
    # ------------------------------------------------------------------

    def test_participation_report_exposes_expected_columns(self):
        """Participation view must expose season_id, club_id, team_count,
        player_count, and tournament_count columns."""
        expected_fields = {
            "season_id",
            "club_id",
            "team_count",
            "player_count",
            "tournament_count",
        }
        self.assertTrue(
            expected_fields.issubset(
                self.env["federation.report.participation"]._fields
            )
        )

    def test_participation_report_counts_team_and_player_for_active_season(self):
        """One active season × one active club should yield a row with
        team_count=1 and player_count=1."""
        row = self.env["federation.report.participation"].search(
            [
                ("season_id", "=", self.season.id),
                ("club_id", "=", self.club.id),
            ],
            limit=1,
        )
        self.assertTrue(row, "Expected a participation row for the seed season+club.")
        self.assertEqual(row.team_count, 1)
        self.assertEqual(row.player_count, 1)

    # ------------------------------------------------------------------
    # federation.report.officiating
    # ------------------------------------------------------------------

    def test_officiating_report_exposes_expected_columns(self):
        """Officiating view must expose referee_id, certification_level,
        assignment_count, and completed_assignment_count columns."""
        expected_fields = {
            "referee_id",
            "certification_level",
            "assignment_count",
            "completed_assignment_count",
        }
        self.assertTrue(
            expected_fields.issubset(self.env["federation.report.officiating"]._fields)
        )

    def test_officiating_report_surfaces_referee_with_zero_assignments(self):
        """An active referee with no assignments should appear with
        assignment_count=0 and a certification_level string."""
        row = self.env["federation.report.officiating"].search(
            [("referee_id", "=", self.referee.id)],
            limit=1,
        )
        self.assertTrue(row, "Expected an officiating row for the seed referee.")
        self.assertEqual(row.assignment_count, 0)
        self.assertEqual(row.completed_assignment_count, 0)
        self.assertTrue(row.certification_level)

    # ------------------------------------------------------------------
    # federation.report.compliance
    # ------------------------------------------------------------------

    def test_compliance_report_exposes_expected_columns(self):
        """Compliance view must expose target_model, compliant_count,
        missing_count, pending_count, expired_count, non_compliant_count."""
        expected_fields = {
            "target_model",
            "compliant_count",
            "missing_count",
            "pending_count",
            "expired_count",
            "non_compliant_count",
        }
        self.assertTrue(
            expected_fields.issubset(self.env["federation.report.compliance"]._fields)
        )

    def test_compliance_report_aggregates_missing_check_for_club_model(self):
        """The seed 'missing' compliance check should increment missing_count
        in the federation.club row of the compliance view."""
        row = self.env["federation.report.compliance"].search(
            [("target_model", "=", "federation.club")],
            limit=1,
        )
        self.assertTrue(row, "Expected a compliance row for federation.club.")
        self.assertGreaterEqual(row.missing_count, 1)
        self.assertEqual(row.compliant_count + row.pending_count + row.expired_count, 0)

    # ------------------------------------------------------------------
    # federation.report.finance
    # ------------------------------------------------------------------

    def test_finance_report_exposes_expected_columns(self):
        """Finance view must expose fee_type_id, state, event_count, and
        total_amount columns."""
        expected_fields = {"fee_type_id", "state", "event_count", "total_amount"}
        self.assertTrue(
            expected_fields.issubset(self.env["federation.report.finance"]._fields)
        )

    def test_finance_report_aggregates_draft_event_amount(self):
        """The seed draft finance event should appear as one row in the
        finance view with the correct total_amount."""
        row = self.env["federation.report.finance"].search(
            [
                ("fee_type_id", "=", self.fee_type.id),
                ("state", "=", "draft"),
            ],
            limit=1,
        )
        self.assertTrue(
            row, "Expected a finance report row for the seed fee type/state."
        )
        self.assertGreaterEqual(row.event_count, 1)
        self.assertGreaterEqual(row.total_amount, 100.00)
