import base64
from datetime import timedelta
from unittest.mock import patch

from odoo.addons.sports_federation_reporting.services import report_schedule_builders
from odoo import fields
from odoo.tests.common import TransactionCase


class TestOperationalReporting(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Ops Club",
                "code": "OPSCL",
                "email": "ops.club@example.com",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Ops Season",
                "code": "OPS2026",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
                "active": True,
            }
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "Ops Team A",
                "club_id": cls.club.id,
                "code": "OPSA",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "Ops Team B",
                "club_id": cls.club.id,
                "code": "OPSB",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Ops Tournament",
                "code": "OPST",
                "season_id": cls.season.id,
                "date_start": "2026-04-01",
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
                "home_score": 1,
                "away_score": 0,
            }
        )
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Ops Rules",
                "code": "OPSR",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )
        cls.standing = cls.env["federation.standing"].create(
            {
                "name": "Ops Standing",
                "tournament_id": cls.tournament.id,
                "rule_set_id": cls.rule_set.id,
            }
        )
        cls.env["federation.standing.line"].create(
            {
                "standing_id": cls.standing.id,
                "participant_id": cls.participant_a.id,
                "rank": 1,
                "played": 1,
                "won": 1,
                "lost": 0,
                "points": 3,
            }
        )
        cls.requirement = cls.env["federation.document.requirement"].create(
            {
                "name": "Ops Insurance",
                "code": "OPSINS",
                "target_model": "federation.club",
                "required_for_all": True,
            }
        )
        cls.env["federation.compliance.check"].create(
            {
                "name": "Ops Club Insurance",
                "target_model": "federation.club",
                "club_id": cls.club.id,
                "status": "missing",
                "requirement_id": cls.requirement.id,
            }
        )
        cls.fee_type = cls.env["federation.fee.type"].create(
            {
                "name": "Ops Venue Fee",
                "code": "OPSFEE",
                "category": "other",
                "default_amount": 55.0,
            }
        )
        cls.finance_event = cls.env["federation.finance.event"].create(
            {
                "name": "Ops Match Charge",
                "fee_type_id": cls.fee_type.id,
                "event_type": "charge",
                "amount": 55.0,
                "source_model": "federation.match",
                "source_res_id": cls.match.id,
                "club_id": cls.club.id,
            }
        )
        cls.player = cls.env["federation.player"].create(
            {
                "first_name": "Ops",
                "last_name": "Player",
                "gender": "male",
            }
        )
        cls.disciplinary_case = cls.env["federation.disciplinary.case"].create(
            {
                "name": "Ops Discipline Case",
                "subject_player_id": cls.player.id,
                "summary": "Case used to test finance exception reporting.",
            }
        )
        cls.fine_sanction = cls.env["federation.sanction"].create(
            {
                "name": "Ops Fine",
                "case_id": cls.disciplinary_case.id,
                "sanction_type": "fine",
                "player_id": cls.player.id,
                "amount": 125.0,
                "effective_date": "2026-04-05",
            }
        )
        cls.env["federation.finance.event"].search(
            [
                ("source_model", "=", "federation.sanction"),
                ("source_res_id", "=", cls.fine_sanction.id),
            ]
        ).unlink()
        cls.failed_notification = cls.env["federation.notification.log"].create(
            {
                "name": "Ops Failed Notification",
                "target_model": "federation.match",
                "target_res_id": cls.match.id,
                "notification_type": "email",
                "template_xmlid": "sports_federation_notifications.template_missing",
                "recipient_email": "ops.alerts@example.com",
                "state": "failed",
                "message": "Template lookup failed.",
            }
        )
        cls.integration_partner = cls.env["federation.integration.partner"].create(
            {
                "name": "Audit Ops Partner",
                "code": "AUDITOPS",
            }
        )
        cls.audit_token_event = cls.env["federation.audit.event"].log_event(
            event_family="integration_token",
            event_type="integration_token_rotated",
            description="Integration partner token rotated through the manager action.",
            target=cls.integration_partner,
            actor=cls.env.user,
            action_name="action_rotate_token",
            changed_fields=["auth_token", "auth_token_last4"],
        )
        stale_dt = fields.Datetime.now() - timedelta(days=4)
        cls.stale_result_match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.team_a.id,
                "away_team_id": cls.team_b.id,
                "state": "done",
                "home_score": 0,
                "away_score": 0,
                "result_state": "verified",
                "result_verified_on": stale_dt,
            }
        )
        cls.stale_override_request = cls.env["federation.override.request"].create(
            {
                "name": "Ops Approved Override",
                "request_type": "standing_adjustment",
                "target_model": "federation.tournament",
                "target_res_id": cls.tournament.id,
                "reason": "Used to test workflow exception reporting.",
                "requested_on": stale_dt,
                "state": "approved",
            }
        )
        cls.team_c = cls.env["federation.team"].create(
            {
                "name": "Ops Team C",
                "club_id": cls.club.id,
                "code": "OPSC",
            }
        )
        cls.season_registration = cls.env["federation.season.registration"].create(
            {
                "season_id": cls.season.id,
                "team_id": cls.team_c.id,
            }
        )
        cls.season_registration.action_submit()
        cls.audit_portal_event = cls.env["federation.audit.event"].log_event(
            event_family="portal_privilege",
            event_type="portal_write",
            description="Portal representative updated a season registration.",
            target=cls.season_registration,
            actor=cls.env.user,
            action_name="write",
            changed_fields=["notes", "state"],
        )
        cls.team_d = cls.env["federation.team"].create(
            {
                "name": "Ops Team D",
                "club_id": cls.club.id,
                "code": "OPSD",
            }
        )
        cls.tournament_registration = cls.env[
            "federation.tournament.registration"
        ].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_d.id,
            }
        )

    def test_operational_report_surfaces_tournament_kpis(self):
        """Test that operational report surfaces tournament kpis."""
        row = self.env["federation.report.operational"].search(
            [
                ("tournament_id", "=", self.tournament.id),
            ],
            limit=1,
        )

        self.assertTrue(row)
        self.assertEqual(row.participant_count, 2)
        self.assertEqual(row.confirmed_participant_count, 2)
        self.assertEqual(row.participant_confirmation_rate, 100.0)
        self.assertEqual(row.completed_match_count, 2)
        self.assertEqual(row.match_completion_rate, 100.0)
        self.assertEqual(row.standing_line_coverage, 1)
        self.assertEqual(row.pending_finance_event_count, 1)
        self.assertEqual(row.pending_finance_amount, 55.0)
        self.assertEqual(row.open_club_compliance_count, 1)
        self.assertEqual(row.readiness_status, "blocked")
        self.assertIn("open compliance checks", row.readiness_note.lower())
        self.assertIn("finance events", row.readiness_note.lower())

    def test_standing_reconciliation_flags_missing_participants(self):
        """Test that standing reconciliation flags missing participants."""
        row = self.env["federation.report.standing.reconciliation"].search(
            [
                ("tournament_id", "=", self.tournament.id),
            ],
            limit=1,
        )

        self.assertTrue(row)
        self.assertEqual(row.confirmed_participant_count, 2)
        self.assertEqual(row.covered_participant_count, 1)
        self.assertEqual(row.missing_participant_count, 1)
        self.assertEqual(row.reconciliation_status, "attention")
        self.assertIn("standing coverage", row.reconciliation_note.lower())

    def test_finance_reconciliation_flags_open_items(self):
        """Test that finance reconciliation flags open items."""
        row = self.env["federation.report.finance.reconciliation"].search(
            [
                ("finance_event_id", "=", self.finance_event.id),
            ],
            limit=1,
        )

        self.assertTrue(row)
        self.assertEqual(row.follow_up_status, "draft")
        self.assertTrue(row.needs_follow_up)
        self.assertEqual(row.counterparty_display, self.club.name)
        self.assertEqual(row.queue_owner_display, "Federation Managers")
        self.assertIn(
            row.sla_status, ("overdue", "escalated", "due_today", "within_sla")
        )

    def test_notification_exception_report_shows_failed_logs(self):
        """Test that notification exception report shows failed logs."""
        row = self.env["federation.report.notification.exception"].search(
            [
                ("notification_log_id", "=", self.failed_notification.id),
            ],
            limit=1,
        )

        self.assertTrue(row)
        self.assertEqual(row.notification_type, "email")
        self.assertEqual(row.recipient_email, "ops.alerts@example.com")
        self.assertIn("Template lookup failed", row.message)
        self.assertIn(
            row.sla_status, ("overdue", "escalated", "due_today", "within_sla")
        )

    def test_finance_exception_report_shows_missing_sanction_event(self):
        """Test that finance exception report shows missing sanction event."""
        row = self.env["federation.report.finance.exception"].search(
            [
                ("sanction_id", "=", self.fine_sanction.id),
            ],
            limit=1,
        )

        self.assertTrue(row)
        self.assertEqual(row.issue_type, "missing_fine_event")
        self.assertEqual(row.expected_amount, 125.0)
        self.assertEqual(row.player_id, self.player)

    def test_workflow_exception_report_surfaces_stalled_result_and_override(self):
        """Test that workflow exception report surfaces stalled result and override."""
        result_row = self.env["federation.report.workflow.exception"].search(
            [
                ("match_id", "=", self.stale_result_match.id),
            ],
            limit=1,
        )
        override_row = self.env["federation.report.workflow.exception"].search(
            [
                ("override_request_id", "=", self.stale_override_request.id),
            ],
            limit=1,
        )

        self.assertTrue(result_row)
        self.assertEqual(result_row.exception_type, "result_approval_stalled")
        self.assertEqual(result_row.tournament_id, self.tournament)
        self.assertGreaterEqual(result_row.age_days, 3)

        self.assertTrue(override_row)
        self.assertEqual(override_row.exception_type, "override_implementation_stalled")
        self.assertGreaterEqual(override_row.age_days, 3)
        self.assertIn(override_row.sla_status, ("overdue", "escalated"))

    def test_compliance_remediation_queue_surfaces_pending_submissions(self):
        """Test that compliance remediation queue surfaces pending submissions."""
        submission = self.env["federation.document.submission"].create(
            {
                "name": "Ops Insurance Submission",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
            }
        )
        submission.action_submit()

        row = self.env["federation.report.compliance.remediation"].search(
            [
                ("submission_id", "=", submission.id),
            ],
            limit=1,
        )

        self.assertTrue(row)
        self.assertEqual(row.status, "submitted")
        self.assertEqual(row.target_display, self.club.name)
        self.assertEqual(row.queue_owner_display, "Compliance Review Queue")
        self.assertIn(
            row.sla_status, ("within_sla", "due_today", "overdue", "escalated")
        )

    def test_compliance_remediation_queue_surfaces_expired_approved_submissions(self):
        """Test that compliance remediation queue surfaces expired approved submissions."""
        submission = self.env["federation.document.submission"].create(
            {
                "name": "Ops Expired Submission",
                "requirement_id": self.requirement.id,
                "club_id": self.club.id,
                "issue_date": fields.Date.today() - timedelta(days=365),
                "expiry_date": fields.Date.today() - timedelta(days=1),
            }
        )
        submission.action_submit()
        submission.action_approve()

        row = self.env["federation.report.compliance.remediation"].search(
            [
                ("submission_id", "=", submission.id),
            ],
            limit=1,
        )

        self.assertTrue(row)
        self.assertEqual(row.status, "expired")
        self.assertIn("renewal", row.remediation_note.lower())

    def test_season_checklist_flags_open_work_for_season(self):
        """Test that season checklist flags open work for season."""
        row = self.env["federation.report.season.checklist"].search(
            [
                ("season_id", "=", self.season.id),
            ],
            limit=1,
        )

        self.assertTrue(row)
        self.assertEqual(row.submitted_season_registration_count, 1)
        self.assertEqual(row.draft_tournament_registration_count, 1)
        self.assertEqual(row.unpublished_tournament_count, 1)
        self.assertGreaterEqual(row.workflow_exception_count, 1)
        self.assertEqual(row.checklist_status, "blocked")
        self.assertIn(
            "season registrations are waiting for staff review",
            row.checklist_note.lower(),
        )

    def test_workflow_exception_schedule_generates_attachment(self):
        """Test that workflow exception schedule generates attachment."""
        schedule = self.env["federation.report.schedule"].create(
            {
                "name": "Workflow Exceptions",
                "report_type": "workflow_exceptions",
                "period_type": "weekly",
                "season_id": self.season.id,
            }
        )

        schedule.action_generate_now()

        self.assertTrue(schedule.generated_file)
        csv_payload = base64.b64decode(schedule.generated_file).decode()
        self.assertIn("Workflow Exceptions", csv_payload)
        self.assertIn(self.stale_result_match.name, csv_payload)

    def test_report_schedule_generates_attachment(self):
        """Test that report schedule generates attachment."""
        schedule = self.env["federation.report.schedule"].create(
            {
                "name": "Weekly Operations",
                "report_type": "operational",
                "period_type": "weekly",
                "season_id": self.season.id,
            }
        )

        schedule.action_generate_now()

        self.assertTrue(schedule.generated_file)
        self.assertTrue(schedule.generated_filename)
        self.assertTrue(schedule.last_run_on)
        self.assertTrue(schedule.next_run_on)
        csv_payload = base64.b64decode(schedule.generated_file).decode()
        self.assertIn("Operational Summary", csv_payload)
        self.assertIn(self.tournament.name, csv_payload)
        self.assertIn("Readiness Note", csv_payload)
        self.assertIn("open compliance checks", csv_payload.lower())
        self.assertEqual(schedule.last_run_status, "success")
        self.assertEqual(schedule.consecutive_failure_count, 0)

    def test_report_schedule_registry_maps_each_type_to_builder_and_action(self):
        """Every scheduled report type should resolve through the shared registry."""
        schedule_model = self.env["federation.report.schedule"]
        self.assertEqual(
            [
                report_type
                for report_type, _label in schedule_model._fields[
                    "report_type"
                ].selection
            ],
            list(report_schedule_builders.REPORT_SPECS),
        )

        for report_type, spec in report_schedule_builders.REPORT_SPECS.items():
            self.assertTrue(callable(spec["builder"]))
            self.assertTrue(spec["action_xmlid"])

            schedule = schedule_model.create(
                {
                    "name": f"Registry {report_type}",
                    "report_type": report_type,
                    "period_type": "weekly",
                    "season_id": self.season.id if spec.get("season_scoped") else False,
                }
            )

            action = schedule.action_open_report()

            self.assertEqual(action["type"], "ir.actions.act_window")
            if spec.get("season_scoped"):
                self.assertEqual(action["domain"], [("season_id", "=", self.season.id)])
            if spec.get("action_context"):
                for key, value in spec["action_context"].items():
                    self.assertEqual(action["context"].get(key), value)

    def test_report_schedule_retention_clears_old_generated_files(self):
        """Retention should clear stale generated report payloads but keep the schedule."""
        schedule = self.env["federation.report.schedule"].create(
            {
                "name": "Retention Operations",
                "report_type": "operational",
                "period_type": "weekly",
                "season_id": self.season.id,
            }
        )

        schedule.action_generate_now()
        old_last_run = fields.Datetime.to_string(
            fields.Datetime.to_datetime(fields.Datetime.now()) - timedelta(days=90)
        )
        schedule.write({"last_run_on": old_last_run})

        cleared = self.env["federation.report.schedule"]._purge_generated_files()
        schedule.invalidate_recordset()

        self.assertEqual(cleared, 1)
        self.assertTrue(schedule.exists())
        self.assertFalse(schedule.generated_file)
        self.assertFalse(schedule.generated_filename)

    def test_schedule_failures_are_persisted_and_visible_in_operator_checklist(self):
        """Test that schedule failures persist and surface in the operator checklist."""
        schedule = self.env["federation.report.schedule"].create(
            {
                "name": "Broken Workflow Export",
                "report_type": "workflow_exceptions",
                "period_type": "weekly",
                "season_id": self.season.id,
            }
        )

        with patch.object(
            type(self.env["federation.report.schedule"]),
            "_build_report_payload",
            autospec=True,
            side_effect=RuntimeError("Simulated schedule failure"),
        ):
            failures = schedule._generate_report()
            self.assertEqual(len(failures), 1)

        self.env["federation.report.schedule"].flush_model(
            [
                "last_run_status",
                "last_failure_on",
                "last_failure_category",
                "last_operator_message",
                "consecutive_failure_count",
            ]
        )
        schedule.invalidate_recordset()
        self.assertEqual(schedule.last_run_status, "failed")
        self.assertEqual(schedule.consecutive_failure_count, 1)
        self.assertTrue(schedule.last_failure_on)
        self.assertEqual(schedule.last_failure_category, "unexpected_bug")
        self.assertFalse(schedule.last_error_message)
        self.assertIn("unexpected server error", schedule.last_operator_message.lower())

        checklist_row = self.env["federation.report.operator.checklist"].search(
            [
                ("queue_code", "=", "scheduled_report_failures"),
            ],
            limit=1,
        )
        self.assertTrue(checklist_row)
        self.assertGreaterEqual(checklist_row.open_count, 1)
        self.assertIn(checklist_row.status, ("attention", "blocked"))

        action = checklist_row.action_open_queue()
        self.assertEqual(action["res_model"], "federation.report.schedule")

    def test_operator_checklist_surfaces_inbound_delivery_failures(self):
        """Test that inbound delivery issues appear in the operator checklist."""
        contract = self.env.ref(
            "sports_federation_import_tools.federation_integration_contract_clubs_csv"
        )
        partner = self.env["federation.integration.partner"].create(
            {
                "name": "Ops Partner",
                "code": "OPS_PARTNER",
            }
        )
        delivery = self.env["federation.integration.delivery"].stage_partner_delivery(
            partner=partner,
            contract=contract,
            filename="ops-clubs.csv",
            payload_base64=base64.b64encode(b"name;code\nOps Club;OPSNEW").decode(
                "utf-8"
            ),
        )
        delivery.action_mark_failed("Preview checksum failed")
        self.env["federation.integration.delivery"].flush_model(
            ["state", "result_message"]
        )

        checklist_row = self.env["federation.report.operator.checklist"].search(
            [
                ("queue_code", "=", "inbound_delivery_failures"),
            ],
            limit=1,
        )
        self.assertTrue(checklist_row)
        self.assertGreaterEqual(checklist_row.open_count, 1)
        self.assertEqual(checklist_row.status, "blocked")

        action = checklist_row.action_open_queue()
        self.assertEqual(action["res_model"], "federation.integration.delivery")

    def test_snapshot_capture_and_board_pack_generation(self):
        """Test that snapshot capture and board pack generation."""
        snapshots = self.env["federation.report.snapshot"].capture_snapshot()

        self.assertTrue(snapshots)
        self.assertEqual(len(snapshots), 5)

        board_pack = self.env["federation.report.schedule"].create(
            {
                "name": "Board Pack",
                "report_type": "board_pack",
                "period_type": "weekly",
            }
        )
        board_pack.action_generate_now()

        self.assertTrue(board_pack.generated_file)
        board_payload = base64.b64decode(board_pack.generated_file).decode()
        self.assertIn("Board Pack", board_payload)
        self.assertIn("Override Backlog", board_payload)

    def test_audit_pack_includes_operational_queues(self):
        """Test that audit pack includes operational queues."""
        schedule = self.env["federation.report.schedule"].create(
            {
                "name": "Audit Pack",
                "report_type": "audit_pack",
                "period_type": "weekly",
            }
        )

        schedule.action_generate_now()

        self.assertTrue(schedule.generated_file)
        audit_payload = base64.b64decode(schedule.generated_file).decode()
        self.assertIn("Audit Pack", audit_payload)
        self.assertIn("Workflow Exceptions", audit_payload)
        self.assertIn("Finance Follow-up", audit_payload)
        self.assertIn("Scheduled Report Failures", audit_payload)
        self.assertIn("Inbound Delivery Failures", audit_payload)

    def test_audit_event_reporting_surfaces_portal_and_token_rows(self):
        """Audit event reporting should expose both portal and token activity rows."""
        portal_row = self.env["federation.report.audit.event"].search(
            [("event_family", "=", "portal_privilege")],
            limit=1,
        )
        token_row = self.env["federation.report.audit.event"].search(
            [("event_family", "=", "integration_token")],
            limit=1,
        )

        self.assertTrue(portal_row)
        self.assertTrue(token_row)
        self.assertEqual(portal_row.event_type, "portal_write")
        self.assertEqual(token_row.event_type, "integration_token_rotated")
        self.assertEqual(
            token_row.target_display_name, self.integration_partner.display_name
        )


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
