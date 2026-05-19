from odoo import fields, models, tools

from .report_operational import FederationReportOperational


class FederationReportSeasonChecklist(models.Model):
    _name = "federation.report.season.checklist"
    _description = "Federation Season Checklist Report"
    _auto = False
    _order = "season_id"

    STATUS_SELECTION = FederationReportOperational.STATUS_SELECTION

    season_id = fields.Many2one("federation.season", string="Season", readonly=True)
    season_state = fields.Char(string="Season State", readonly=True)
    draft_season_registration_count = fields.Integer(
        string="Draft Season Registrations",
        readonly=True,
    )
    submitted_season_registration_count = fields.Integer(
        string="Submitted Season Registrations",
        readonly=True,
    )
    draft_tournament_registration_count = fields.Integer(
        string="Draft Tournament Registrations",
        readonly=True,
    )
    submitted_tournament_registration_count = fields.Integer(
        string="Submitted Tournament Registrations",
        readonly=True,
    )
    live_tournament_count = fields.Integer(string="Live Tournaments", readonly=True)
    published_tournament_count = fields.Integer(
        string="Published Tournaments",
        readonly=True,
    )
    unpublished_tournament_count = fields.Integer(
        string="Unpublished Tournaments",
        readonly=True,
    )
    workflow_exception_count = fields.Integer(
        string="Workflow Exceptions",
        readonly=True,
    )
    checklist_status = fields.Selection(
        STATUS_SELECTION,
        string="Checklist Status",
        readonly=True,
    )
    checklist_note = fields.Text(string="Checklist Note", readonly=True)

    def init(self):
        """Rebuild the SQL view so seasonal checklist columns stay schema-safe."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_season_checklist AS (
                -- block: season_registration_stats
                WITH season_registration_stats AS (
                    SELECT
                        reg.season_id,
                        COUNT(*) FILTER (WHERE reg.state = 'draft') AS draft_season_registration_count,
                        COUNT(*) FILTER (WHERE reg.state = 'submitted') AS submitted_season_registration_count
                    FROM federation_season_registration reg
                    GROUP BY reg.season_id
                ),
                -- block: tournament_registration_stats
                tournament_registration_stats AS (
                    SELECT
                        t.season_id,
                        COUNT(*) FILTER (WHERE reg.state = 'draft') AS draft_tournament_registration_count,
                        COUNT(*) FILTER (WHERE reg.state = 'submitted') AS submitted_tournament_registration_count
                    FROM federation_tournament_registration reg
                    JOIN federation_tournament t ON t.id = reg.tournament_id
                    GROUP BY t.season_id
                ),
                -- block: tournament_stats
                tournament_stats AS (
                    SELECT
                        t.season_id,
                        COUNT(*) FILTER (WHERE t.state IN ('open', 'in_progress')) AS live_tournament_count,
                        COUNT(*) FILTER (WHERE COALESCE(t.website_published, FALSE)) AS published_tournament_count,
                        COUNT(*) FILTER (WHERE NOT COALESCE(t.website_published, FALSE)) AS unpublished_tournament_count
                    FROM federation_tournament t
                    GROUP BY t.season_id
                ),
                -- block: workflow_stats
                workflow_stats AS (
                    SELECT
                        queue.season_id,
                        COUNT(*) AS workflow_exception_count
                    FROM (
                        SELECT t.season_id
                        FROM federation_match m
                        JOIN federation_tournament t ON t.id = m.tournament_id
                        WHERE (
                            (m.result_state = 'submitted' AND m.result_submitted_on IS NOT NULL AND m.result_submitted_on <= (NOW() - INTERVAL '2 day'))
                            OR (m.result_state = 'verified' AND m.result_verified_on IS NOT NULL AND m.result_verified_on <= (NOW() - INTERVAL '2 day'))
                        )

                        UNION ALL

                        SELECT t.season_id
                        FROM federation_override_request req
                        JOIN federation_tournament t
                          ON req.target_model = 'federation.tournament'
                         AND req.target_res_id = t.id
                        WHERE (
                            (req.state = 'submitted' AND req.requested_on <= (NOW() - INTERVAL '3 day'))
                            OR (req.state = 'approved' AND req.requested_on <= (NOW() - INTERVAL '3 day'))
                        )
                    ) queue
                    GROUP BY queue.season_id
                )
                -- block: report_rows
                SELECT
                    row_number() OVER (ORDER BY s.id) AS id,
                    s.id AS season_id,
                    s.state::varchar AS season_state,
                    COALESCE(srs.draft_season_registration_count, 0) AS draft_season_registration_count,
                    COALESCE(srs.submitted_season_registration_count, 0) AS submitted_season_registration_count,
                    COALESCE(trs.draft_tournament_registration_count, 0) AS draft_tournament_registration_count,
                    COALESCE(trs.submitted_tournament_registration_count, 0) AS submitted_tournament_registration_count,
                    COALESCE(ts.live_tournament_count, 0) AS live_tournament_count,
                    COALESCE(ts.published_tournament_count, 0) AS published_tournament_count,
                    COALESCE(ts.unpublished_tournament_count, 0) AS unpublished_tournament_count,
                    COALESCE(ws.workflow_exception_count, 0) AS workflow_exception_count,
                    CASE
                        WHEN COALESCE(srs.submitted_season_registration_count, 0) > 0
                          OR COALESCE(trs.submitted_tournament_registration_count, 0) > 0
                          OR COALESCE(ws.workflow_exception_count, 0) > 0
                        THEN 'blocked'
                        WHEN COALESCE(srs.draft_season_registration_count, 0) > 0
                          OR COALESCE(trs.draft_tournament_registration_count, 0) > 0
                          OR (
                              COALESCE(ts.live_tournament_count, 0) > 0
                              AND COALESCE(ts.unpublished_tournament_count, 0) > 0
                          )
                        THEN 'attention'
                        ELSE 'healthy'
                    END AS checklist_status,
                    CASE
                        WHEN COALESCE(srs.submitted_season_registration_count, 0) > 0 THEN 'Season registrations are waiting for staff review.'
                        WHEN COALESCE(trs.submitted_tournament_registration_count, 0) > 0 THEN 'Tournament registrations are waiting for staff review.'
                        WHEN COALESCE(ws.workflow_exception_count, 0) > 0 THEN 'Workflow exceptions must be cleared before seasonal operations are considered healthy.'
                        WHEN COALESCE(srs.draft_season_registration_count, 0) > 0 THEN 'Draft season registrations still need operator follow-up.'
                        WHEN COALESCE(trs.draft_tournament_registration_count, 0) > 0 THEN 'Draft tournament registrations still need operator follow-up.'
                        WHEN COALESCE(ts.live_tournament_count, 0) > 0 AND COALESCE(ts.unpublished_tournament_count, 0) > 0 THEN 'Some live tournaments are not yet published on the public site.'
                        ELSE 'Season operations checklist is currently clear.'
                    END AS checklist_note
                FROM federation_season s
                LEFT JOIN season_registration_stats srs ON srs.season_id = s.id
                LEFT JOIN tournament_registration_stats trs ON trs.season_id = s.id
                LEFT JOIN tournament_stats ts ON ts.season_id = s.id
                LEFT JOIN workflow_stats ws ON ws.season_id = s.id
            )
            """)
