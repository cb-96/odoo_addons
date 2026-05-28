from odoo import fields, models, tools

from .report_operational import FederationReportOperational


class FederationReportWorkflowException(models.Model):
    _name = "federation.report.workflow.exception"
    _description = "Federation Workflow Exception Report"
    _auto = False
    _order = "age_days desc, raised_on asc"

    EXCEPTION_TYPE_SELECTION = [
        ("result_submission_stalled", "Result Verification Backlog"),
        ("result_approval_stalled", "Result Approval Backlog"),
        ("override_review_stalled", "Override Review Backlog"),
        ("override_implementation_stalled", "Override Implementation Backlog"),
    ]

    season_id = fields.Many2one("federation.season", string="Season", readonly=True)
    tournament_id = fields.Many2one(
        "federation.tournament", string="Tournament", readonly=True
    )
    match_id = fields.Many2one("federation.match", string="Match", readonly=True)
    override_request_id = fields.Many2one(
        "federation.override.request",
        string="Override Request",
        readonly=True,
    )
    source_model = fields.Char(string="Source Model", readonly=True)
    source_res_id = fields.Integer(string="Source Record ID", readonly=True)
    reference_name = fields.Char(string="Reference", readonly=True)
    state = fields.Char(string="State", readonly=True)
    responsible_user_id = fields.Many2one(
        "res.users",
        string="Responsible User",
        readonly=True,
    )
    raised_on = fields.Datetime(string="Raised On", readonly=True)
    age_days = fields.Integer(string="Age (Days)", readonly=True)
    queue_owner_display = fields.Char(string="Queue Owner", readonly=True)
    sla_due_on = fields.Datetime(string="SLA Due On", readonly=True)
    sla_status = fields.Selection(
        FederationReportOperational.SLA_STATUS_SELECTION,
        string="SLA Status",
        readonly=True,
    )
    exception_type = fields.Selection(
        EXCEPTION_TYPE_SELECTION,
        string="Exception Type",
        readonly=True,
    )
    exception_note = fields.Text(string="Exception Note", readonly=True)

    def init(self):
        """Rebuild the SQL view so workflow backlog rows match the declared fields."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_workflow_exception AS (
                -- block: queue
                WITH queue AS (
                    SELECT
                        se.id AS season_id,
                        t.id AS tournament_id,
                        m.id AS match_id,
                        NULL::integer AS override_request_id,
                        'federation.match'::varchar AS source_model,
                        m.id AS source_res_id,
                        m.name AS reference_name,
                        m.result_state::varchar AS state,
                        m.result_submitted_by_id AS responsible_user_id,
                        m.result_submitted_on AS raised_on,
                        (m.result_submitted_on + INTERVAL '2 day') AS sla_due_on,
                        (CURRENT_DATE - m.result_submitted_on::date)::int AS age_days,
                        'result_submission_stalled'::varchar AS exception_type,
                        'Submitted result is still waiting for verification.'::text AS exception_note
                    FROM federation_match m
                    LEFT JOIN federation_tournament t ON t.id = m.tournament_id
                    LEFT JOIN federation_season se ON se.id = t.season_id
                    WHERE m.result_state = 'submitted'
                      AND m.result_submitted_on IS NOT NULL
                      AND m.result_submitted_on <= (NOW() - INTERVAL '2 day')

                    UNION ALL

                    SELECT
                        se.id AS season_id,
                        t.id AS tournament_id,
                        m.id AS match_id,
                        NULL::integer AS override_request_id,
                        'federation.match'::varchar AS source_model,
                        m.id AS source_res_id,
                        m.name AS reference_name,
                        m.result_state::varchar AS state,
                        m.result_verified_by_id AS responsible_user_id,
                        m.result_verified_on AS raised_on,
                        (m.result_verified_on + INTERVAL '2 day') AS sla_due_on,
                        (CURRENT_DATE - m.result_verified_on::date)::int AS age_days,
                        'result_approval_stalled'::varchar AS exception_type,
                        'Verified result is still waiting for approval.'::text AS exception_note
                    FROM federation_match m
                    LEFT JOIN federation_tournament t ON t.id = m.tournament_id
                    LEFT JOIN federation_season se ON se.id = t.season_id
                    WHERE m.result_state = 'verified'
                      AND m.result_verified_on IS NOT NULL
                      AND m.result_verified_on <= (NOW() - INTERVAL '2 day')

                    UNION ALL

                    SELECT
                        NULL::integer AS season_id,
                        NULL::integer AS tournament_id,
                        NULL::integer AS match_id,
                        req.id AS override_request_id,
                        'federation.override.request'::varchar AS source_model,
                        req.id AS source_res_id,
                        req.name AS reference_name,
                        req.state::varchar AS state,
                        req.requested_by_id AS responsible_user_id,
                        req.requested_on AS raised_on,
                        (req.requested_on + INTERVAL '3 day') AS sla_due_on,
                        (CURRENT_DATE - req.requested_on::date)::int AS age_days,
                        'override_review_stalled'::varchar AS exception_type,
                        'Submitted override request is still waiting for governance review.'::text AS exception_note
                    FROM federation_override_request req
                    WHERE req.state = 'submitted'
                      AND req.requested_on <= (NOW() - INTERVAL '3 day')

                    UNION ALL

                    SELECT
                        NULL::integer AS season_id,
                        NULL::integer AS tournament_id,
                        NULL::integer AS match_id,
                        req.id AS override_request_id,
                        'federation.override.request'::varchar AS source_model,
                        req.id AS source_res_id,
                        req.name AS reference_name,
                        req.state::varchar AS state,
                        req.requested_by_id AS responsible_user_id,
                        req.requested_on AS raised_on,
                        (req.requested_on + INTERVAL '3 day') AS sla_due_on,
                        (CURRENT_DATE - req.requested_on::date)::int AS age_days,
                        'override_implementation_stalled'::varchar AS exception_type,
                        'Approved override request is still waiting to be implemented.'::text AS exception_note
                    FROM federation_override_request req
                    WHERE req.state = 'approved'
                      AND req.requested_on <= (NOW() - INTERVAL '3 day')
                )
                -- block: report_rows
                SELECT
                    row_number() OVER (
                        ORDER BY age_days DESC, raised_on ASC, source_model ASC, source_res_id ASC
                    ) AS id,
                    queue.season_id,
                    queue.tournament_id,
                    queue.match_id,
                    queue.override_request_id,
                    queue.source_model,
                    queue.source_res_id,
                    queue.reference_name,
                    queue.state,
                    queue.responsible_user_id,
                    queue.raised_on,
                    COALESCE(rp.name, 'Federation Managers') AS queue_owner_display,
                    queue.sla_due_on,
                    CASE
                        WHEN CURRENT_TIMESTAMP < queue.sla_due_on THEN 'within_sla'
                        WHEN CURRENT_DATE = queue.sla_due_on::date THEN 'due_today'
                        WHEN CURRENT_TIMESTAMP < (queue.sla_due_on + INTERVAL '2 day') THEN 'overdue'
                        ELSE 'escalated'
                    END AS sla_status,
                    queue.age_days,
                    queue.exception_type,
                    queue.exception_note
                FROM queue
                LEFT JOIN res_users ru ON ru.id = queue.responsible_user_id
                LEFT JOIN res_partner rp ON rp.id = ru.partner_id
            )
            """)
