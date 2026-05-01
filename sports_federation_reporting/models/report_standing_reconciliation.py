from odoo import fields, models, tools

from .report_operational import FederationReportOperational


class FederationReportStandingReconciliation(models.Model):
    _name = "federation.report.standing.reconciliation"
    _description = "Federation Standing Reconciliation Report"
    _auto = False
    _order = "season_id, tournament_id"

    STATUS_SELECTION = FederationReportOperational.STATUS_SELECTION
    TOURNAMENT_STATE_SELECTION = FederationReportOperational.TOURNAMENT_STATE_SELECTION

    season_id = fields.Many2one("federation.season", string="Season", readonly=True)
    tournament_id = fields.Many2one(
        "federation.tournament", string="Tournament", readonly=True
    )
    tournament_state = fields.Selection(
        TOURNAMENT_STATE_SELECTION, string="Tournament State", readonly=True
    )
    confirmed_participant_count = fields.Integer(
        string="Confirmed Participants", readonly=True
    )
    covered_participant_count = fields.Integer(
        string="Covered Participants", readonly=True
    )
    frozen_standing_count = fields.Integer(string="Frozen Standings", readonly=True)
    missing_participant_count = fields.Integer(
        string="Missing Participants", readonly=True
    )
    orphaned_participant_count = fields.Integer(
        string="Orphaned Participants", readonly=True
    )
    reconciliation_status = fields.Selection(
        STATUS_SELECTION, string="Reconciliation Status", readonly=True
    )
    reconciliation_note = fields.Text(string="Reconciliation Note", readonly=True)

    def init(self):
        """Rebuild the SQL view so reconciliation columns stay registry-aligned."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_standing_reconciliation AS (
                -- block: participant_stats
                WITH participant_stats AS (
                    SELECT
                        p.tournament_id,
                        COUNT(*) FILTER (WHERE p.state = 'confirmed') AS confirmed_participant_count
                    FROM federation_tournament_participant p
                    GROUP BY p.tournament_id
                ),
                -- block: coverage_stats
                coverage_stats AS (
                    SELECT
                        s.tournament_id,
                        COUNT(DISTINCT sl.participant_id) AS covered_participant_count,
                        COUNT(DISTINCT s.id) FILTER (WHERE s.state = 'frozen') AS frozen_standing_count
                    FROM federation_standing s
                    LEFT JOIN federation_standing_line sl ON sl.standing_id = s.id
                    GROUP BY s.tournament_id
                )
                -- block: report_rows
                SELECT
                    row_number() OVER (ORDER BY se.id, t.id) AS id,
                    se.id AS season_id,
                    t.id AS tournament_id,
                    t.state AS tournament_state,
                    COALESCE(ps.confirmed_participant_count, 0) AS confirmed_participant_count,
                    COALESCE(cs.covered_participant_count, 0) AS covered_participant_count,
                    COALESCE(cs.frozen_standing_count, 0) AS frozen_standing_count,
                    GREATEST(COALESCE(ps.confirmed_participant_count, 0) - COALESCE(cs.covered_participant_count, 0), 0) AS missing_participant_count,
                    GREATEST(COALESCE(cs.covered_participant_count, 0) - COALESCE(ps.confirmed_participant_count, 0), 0) AS orphaned_participant_count,
                    CASE
                        WHEN COALESCE(ps.confirmed_participant_count, 0) > 0 AND COALESCE(cs.covered_participant_count, 0) = 0 THEN 'blocked'
                        WHEN COALESCE(ps.confirmed_participant_count, 0) <> COALESCE(cs.covered_participant_count, 0)
                          OR (
                              t.state IN ('in_progress', 'closed')
                              AND COALESCE(cs.frozen_standing_count, 0) = 0
                              AND COALESCE(ps.confirmed_participant_count, 0) > 0
                          )
                        THEN 'attention'
                        ELSE 'healthy'
                    END AS reconciliation_status,
                    CASE
                        WHEN COALESCE(ps.confirmed_participant_count, 0) > 0 AND COALESCE(cs.covered_participant_count, 0) = 0 THEN 'No standing lines currently cover confirmed participants.'
                        WHEN COALESCE(ps.confirmed_participant_count, 0) <> COALESCE(cs.covered_participant_count, 0) THEN 'Confirmed participant count does not match standing coverage.'
                        WHEN t.state IN ('in_progress', 'closed')
                          AND COALESCE(cs.frozen_standing_count, 0) = 0
                          AND COALESCE(ps.confirmed_participant_count, 0) > 0 THEN 'Tournament has confirmed participants but no frozen standings snapshot.'
                        ELSE 'Standings coverage matches confirmed tournament participants.'
                    END AS reconciliation_note
                FROM federation_tournament t
                LEFT JOIN federation_season se ON se.id = t.season_id
                LEFT JOIN participant_stats ps ON ps.tournament_id = t.id
                LEFT JOIN coverage_stats cs ON cs.tournament_id = t.id
            )
            """)
