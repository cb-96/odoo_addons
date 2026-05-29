import base64

from odoo.tests.common import TransactionCase


class TestYearFourReporting(TransactionCase):

    def _get_plan_text(self, sql, params=None):
        """Return the textual PostgreSQL plan for the supplied statement."""
        self.env.cr.execute(f"EXPLAIN {sql}", params or [])
        return "\n".join(line[0] for line in self.env.cr.fetchall())

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club_a = cls.env["federation.club"].create(
            {
                "name": "North Club",
                "code": "NORTH",
                "email": "north@example.com",
            }
        )
        cls.club_b = cls.env["federation.club"].create(
            {
                "name": "South Club",
                "code": "SOUTH",
                "email": "south@example.com",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Planning Season",
                "code": "PLAN2026",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "active": True,
                "target_club_count": 2,
                "target_team_count": 2,
                "target_tournament_count": 1,
                "target_participant_count": 2,
            }
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "North United",
                "club_id": cls.club_a.id,
                "code": "NRTHU",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "South City",
                "club_id": cls.club_b.id,
                "code": "STHCT",
            }
        )
        cls.registration_a = cls.env["federation.season.registration"].create(
            {
                "season_id": cls.season.id,
                "team_id": cls.team_a.id,
            }
        )
        cls.registration_b = cls.env["federation.season.registration"].create(
            {
                "season_id": cls.season.id,
                "team_id": cls.team_b.id,
            }
        )
        cls.registration_a.action_confirm()
        cls.registration_b.action_confirm()
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Planning Cup",
                "code": "PLANCUP",
                "season_id": cls.season.id,
                "date_start": "2026-03-10",
                "state": "in_progress",
            }
        )
        cls.participant_a = cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_a.id,
                "state": "confirmed",
            }
        )
        cls.participant_b = cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_b.id,
                "state": "confirmed",
            }
        )
        cls.match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.team_a.id,
                "away_team_id": cls.team_b.id,
                "state": "done",
                "home_score": 2,
                "away_score": 1,
            }
        )
        cls.fee_type = cls.env["federation.fee.type"].create(
            {
                "name": "Season Operations",
                "code": "PLANFEE",
                "category": "other",
                "default_amount": 500.0,
            }
        )
        cls.env["federation.season.budget"].create(
            {
                "season_id": cls.season.id,
                "fee_type_id": cls.fee_type.id,
                "budget_amount": 500.0,
            }
        )
        cls.confirmed_finance_event = cls.env["federation.finance.event"].create(
            {
                "name": "Confirmed Match Charge",
                "fee_type_id": cls.fee_type.id,
                "event_type": "charge",
                "amount": 300.0,
                "state": "confirmed",
                "source_model": "federation.match",
                "source_res_id": cls.match.id,
                "club_id": cls.club_a.id,
            }
        )
        cls.pending_finance_event = cls.env["federation.finance.event"].create(
            {
                "name": "Pending Registration Charge",
                "fee_type_id": cls.fee_type.id,
                "event_type": "charge",
                "amount": 75.0,
                "state": "draft",
                "source_model": "federation.season.registration",
                "source_res_id": cls.registration_a.id,
                "club_id": cls.club_a.id,
            }
        )
        cls.requirement = cls.env["federation.document.requirement"].create(
            {
                "name": "Season Safeguarding",
                "code": "PLANGUARD",
                "target_model": "federation.club",
                "required_for_all": True,
            }
        )
        cls.compliance_check = cls.env["federation.compliance.check"].create(
            {
                "name": "South Club Safeguarding",
                "target_model": "federation.club",
                "club_id": cls.club_b.id,
                "status": "missing",
                "requirement_id": cls.requirement.id,
            }
        )

    def test_season_portfolio_report_rolls_up_targets_and_budget(self):
        """Test that season portfolio report rolls up targets and budget."""
        row = self.env["federation.report.season.portfolio"].search(
            [
                ("season_id", "=", self.season.id),
            ],
            limit=1,
        )

        self.assertTrue(row)
        self.assertEqual(row.actual_club_count, 2)
        self.assertEqual(row.actual_team_count, 2)
        self.assertEqual(row.actual_tournament_count, 1)
        self.assertEqual(row.actual_participant_count, 2)
        self.assertEqual(row.budget_amount, 500.0)
        self.assertEqual(row.actual_finance_amount, 300.0)
        self.assertEqual(row.budget_variance_amount, -200.0)
        self.assertEqual(row.open_compliance_item_count, 1)
        self.assertEqual(row.planning_status, "blocked")
        self.assertIn("compliance", row.planning_note.lower())

    def test_club_performance_report_surfaces_finance_and_compliance_status(self):
        """Test that club performance report surfaces finance and compliance status."""
        north_row = self.env["federation.report.club.performance"].search(
            [
                ("season_id", "=", self.season.id),
                ("club_id", "=", self.club_a.id),
            ],
            limit=1,
        )
        south_row = self.env["federation.report.club.performance"].search(
            [
                ("season_id", "=", self.season.id),
                ("club_id", "=", self.club_b.id),
            ],
            limit=1,
        )

        self.assertTrue(north_row)
        self.assertEqual(north_row.confirmed_team_count, 1)
        self.assertEqual(north_row.confirmed_tournament_entry_count, 1)
        self.assertEqual(north_row.completed_match_count, 1)
        self.assertEqual(north_row.win_count, 1)
        self.assertEqual(north_row.goal_difference, 1)
        self.assertEqual(north_row.pending_finance_event_count, 3)
        self.assertEqual(north_row.open_compliance_item_count, 0)
        self.assertEqual(north_row.performance_status, "attention")
        self.assertIn("finance", north_row.performance_note.lower())

        self.assertTrue(south_row)
        self.assertEqual(south_row.loss_count, 1)
        self.assertEqual(south_row.open_compliance_item_count, 1)
        self.assertEqual(south_row.performance_status, "blocked")
        self.assertIn("compliance", south_row.performance_note.lower())

    def test_year_four_report_schedules_generate_and_open(self):
        """Test that year four report schedules generate and open."""
        portfolio_schedule = self.env["federation.report.schedule"].create(
            {
                "name": "Season Portfolio",
                "report_type": "season_portfolio",
                "period_type": "monthly",
                "season_id": self.season.id,
            }
        )
        club_schedule = self.env["federation.report.schedule"].create(
            {
                "name": "Club Performance",
                "report_type": "club_performance",
                "period_type": "weekly",
                "season_id": self.season.id,
            }
        )

        portfolio_schedule.action_generate_now()
        club_schedule.action_generate_now()

        portfolio_payload = base64.b64decode(portfolio_schedule.generated_file).decode()
        club_payload = base64.b64decode(club_schedule.generated_file).decode()

        self.assertIn("Season Portfolio", portfolio_payload)
        self.assertIn(self.season.name, portfolio_payload)
        self.assertIn("Club Performance", club_payload)
        self.assertIn(self.club_a.name, club_payload)

        portfolio_action = portfolio_schedule.action_open_report()
        club_action = club_schedule.action_open_report()

        self.assertEqual(
            portfolio_action["res_model"], "federation.report.season.portfolio"
        )
        self.assertEqual(
            portfolio_action["domain"], [("season_id", "=", self.season.id)]
        )
        self.assertEqual(club_action["res_model"], "federation.report.club.performance")
        self.assertEqual(club_action["domain"], [("season_id", "=", self.season.id)])

    def test_year_four_report_builders_stay_within_query_budget(self):
        """The heavy planning report builders keep stable ORM query budgets."""
        portfolio_schedule = self.env["federation.report.schedule"].create(
            {
                "name": "Budgeted Season Portfolio",
                "report_type": "season_portfolio",
                "period_type": "monthly",
                "season_id": self.season.id,
            }
        )
        club_schedule = self.env["federation.report.schedule"].create(
            {
                "name": "Budgeted Club Performance",
                "report_type": "club_performance",
                "period_type": "weekly",
                "season_id": self.season.id,
            }
        )

        with self.assertQueryCount(3):
            _headers, portfolio_rows, _slug = (
                portfolio_schedule._build_season_portfolio_rows()
            )
        with self.assertQueryCount(4):
            _headers, club_rows, _slug = club_schedule._build_club_performance_rows()

        self.assertTrue(portfolio_rows)
        self.assertTrue(club_rows)

    def test_year_four_report_plan_watchpoints_capture_heavy_operators(self):
        """The large SQL reports still expose the known aggregate and sort plan operators."""
        season_plan = self._get_plan_text(
            "SELECT * FROM federation_report_season_portfolio WHERE season_id = %s",
            [self.season.id],
        )
        club_plan = self._get_plan_text(
            "SELECT * FROM federation_report_club_performance WHERE season_id = %s",
            [self.season.id],
        )

        self.assertRegex(season_plan, r"HashAggregate|GroupAggregate|WindowAgg|Sort")
        self.assertRegex(club_plan, r"HashAggregate|GroupAggregate|WindowAgg|Sort")
