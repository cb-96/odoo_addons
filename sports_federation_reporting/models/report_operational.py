from odoo import fields, models, tools


class FederationReportOperational(models.Model):
    _name = "federation.report.operational"
    _description = "Federation Operational Report"
    _auto = False
    _order = "season_id, tournament_id"

    STATUS_SELECTION = [
        ("healthy", "Healthy"),
        ("attention", "Attention"),
        ("blocked", "Blocked"),
    ]
    SLA_STATUS_SELECTION = [
        ("within_sla", "Within SLA"),
        ("due_today", "Due Today"),
        ("overdue", "Overdue"),
        ("escalated", "Escalated"),
        ("complete", "Complete"),
        ("cancelled", "Cancelled"),
    ]

    TOURNAMENT_STATE_SELECTION = [
        ("draft", "Draft"),
        ("open", "Open"),
        ("in_progress", "In Progress"),
        ("closed", "Closed"),
        ("cancelled", "Cancelled"),
    ]

    season_id = fields.Many2one("federation.season", string="Season", readonly=True)
    tournament_id = fields.Many2one(
        "federation.tournament", string="Tournament", readonly=True
    )
    tournament_state = fields.Selection(
        TOURNAMENT_STATE_SELECTION, string="Tournament State", readonly=True
    )
    date_start = fields.Date(string="Start Date", readonly=True)
    date_end = fields.Date(string="End Date", readonly=True)
    participant_count = fields.Integer(string="Participants", readonly=True)
    confirmed_participant_count = fields.Integer(
        string="Confirmed Participants", readonly=True
    )
    participant_confirmation_rate = fields.Float(
        string="Participant Confirmation %", readonly=True, digits=(16, 2)
    )
    match_count = fields.Integer(string="Matches", readonly=True)
    completed_match_count = fields.Integer(string="Completed Matches", readonly=True)
    match_completion_rate = fields.Float(
        string="Match Completion %", readonly=True, digits=(16, 2)
    )
    frozen_standing_count = fields.Integer(string="Frozen Standings", readonly=True)
    standing_line_coverage = fields.Integer(string="Standing Coverage", readonly=True)
    pending_finance_event_count = fields.Integer(
        string="Pending Finance Events", readonly=True
    )
    pending_finance_amount = fields.Float(
        string="Pending Finance Amount", readonly=True
    )
    open_club_compliance_count = fields.Integer(
        string="Open Club Compliance Checks", readonly=True
    )
    readiness_status = fields.Selection(
        STATUS_SELECTION, string="Readiness Status", readonly=True
    )
    readiness_note = fields.Text(string="Readiness Note", readonly=True)

    def init(self):
        """Rebuild the SQL view during install and upgrade.

        This keeps the registry field map aligned with the extracted reporting
        query blocks after schema or join changes.
        """
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_operational AS (
                -- block: participant_stats
                WITH participant_stats AS (
                    SELECT
                        p.tournament_id,
                        COUNT(*) AS participant_count,
                        COUNT(*) FILTER (WHERE p.state = 'confirmed') AS confirmed_participant_count
                    FROM federation_tournament_participant p
                    GROUP BY p.tournament_id
                ),
                -- block: match_stats
                match_stats AS (
                    SELECT
                        m.tournament_id,
                        COUNT(*) AS match_count,
                        COUNT(*) FILTER (WHERE m.state = 'done') AS completed_match_count
                    FROM federation_match m
                    GROUP BY m.tournament_id
                ),
                -- block: standing_stats
                standing_stats AS (
                    SELECT
                        s.tournament_id,
                        COUNT(*) FILTER (WHERE s.state = 'frozen') AS frozen_standing_count,
                        COUNT(DISTINCT sl.participant_id) AS standing_line_coverage
                    FROM federation_standing s
                    LEFT JOIN federation_standing_line sl ON sl.standing_id = s.id
                    GROUP BY s.tournament_id
                ),
                -- block: finance_links
                finance_links AS (
                    SELECT fe.id, fe.state, fe.amount, m.tournament_id
                    FROM federation_finance_event fe
                    JOIN federation_match m
                      ON fe.source_model = 'federation.match'
                     AND fe.source_res_id = m.id

                    UNION ALL

                    SELECT fe.id, fe.state, fe.amount, m.tournament_id
                    FROM federation_finance_event fe
                    JOIN federation_match_referee mr
                      ON fe.source_model = 'federation.match.referee'
                     AND fe.source_res_id = mr.id
                    JOIN federation_match m ON m.id = mr.match_id
                ),
                -- block: finance_stats
                finance_stats AS (
                    SELECT
                        fl.tournament_id,
                        COUNT(DISTINCT fl.id) FILTER (WHERE fl.state IN ('draft', 'confirmed')) AS pending_finance_event_count,
                        COALESCE(SUM(fl.amount) FILTER (WHERE fl.state IN ('draft', 'confirmed')), 0) AS pending_finance_amount
                    FROM finance_links fl
                    GROUP BY fl.tournament_id
                ),
                -- block: club_compliance_stats
                club_compliance_stats AS (
                    SELECT
                        p.tournament_id,
                        COUNT(DISTINCT cc.id) AS open_club_compliance_count
                    FROM federation_tournament_participant p
                    JOIN federation_compliance_check cc
                      ON cc.club_id = p.club_id
                     AND cc.status <> 'compliant'
                    GROUP BY p.tournament_id
                )
                -- block: report_rows
                SELECT
                    row_number() OVER (ORDER BY s.id, t.id) AS id,
                    s.id AS season_id,
                    t.id AS tournament_id,
                    t.state AS tournament_state,
                    t.date_start,
                    t.date_end,
                    COALESCE(ps.participant_count, 0) AS participant_count,
                    COALESCE(ps.confirmed_participant_count, 0) AS confirmed_participant_count,
                    ROUND(
                        CASE
                            WHEN COALESCE(ps.participant_count, 0) = 0 THEN 0
                            ELSE (COALESCE(ps.confirmed_participant_count, 0)::numeric / ps.participant_count::numeric) * 100
                        END,
                        2
                    ) AS participant_confirmation_rate,
                    COALESCE(ms.match_count, 0) AS match_count,
                    COALESCE(ms.completed_match_count, 0) AS completed_match_count,
                    ROUND(
                        CASE
                            WHEN COALESCE(ms.match_count, 0) = 0 THEN 0
                            ELSE (COALESCE(ms.completed_match_count, 0)::numeric / ms.match_count::numeric) * 100
                        END,
                        2
                    ) AS match_completion_rate,
                    COALESCE(ss.frozen_standing_count, 0) AS frozen_standing_count,
                    COALESCE(ss.standing_line_coverage, 0) AS standing_line_coverage,
                    COALESCE(fs.pending_finance_event_count, 0) AS pending_finance_event_count,
                    COALESCE(fs.pending_finance_amount, 0) AS pending_finance_amount,
                    COALESCE(ccs.open_club_compliance_count, 0) AS open_club_compliance_count,
                    CASE
                        WHEN COALESCE(ccs.open_club_compliance_count, 0) > 0 THEN 'blocked'
                        WHEN COALESCE(ps.participant_count, 0) > COALESCE(ps.confirmed_participant_count, 0)
                          OR (
                              COALESCE(ms.match_count, 0) > 0
                              AND COALESCE(ms.completed_match_count, 0) < COALESCE(ms.match_count, 0)
                          )
                          OR COALESCE(fs.pending_finance_event_count, 0) > 0
                        THEN 'attention'
                        ELSE 'healthy'
                    END AS readiness_status,
                    CASE
                        WHEN COALESCE(ccs.open_club_compliance_count, 0) > 0
                          OR COALESCE(ps.participant_count, 0) > COALESCE(ps.confirmed_participant_count, 0)
                          OR (
                              COALESCE(ms.match_count, 0) > 0
                              AND COALESCE(ms.completed_match_count, 0) < COALESCE(ms.match_count, 0)
                          )
                          OR COALESCE(fs.pending_finance_event_count, 0) > 0
                        THEN CONCAT_WS(
                            ' ',
                            CASE
                                WHEN COALESCE(ccs.open_club_compliance_count, 0) > 0 THEN 'Participating clubs still have open compliance checks.'
                            END,
                            CASE
                                WHEN COALESCE(ps.participant_count, 0) > COALESCE(ps.confirmed_participant_count, 0) THEN 'Participant confirmations are still incomplete.'
                            END,
                            CASE
                                WHEN COALESCE(ms.match_count, 0) > 0
                                  AND COALESCE(ms.completed_match_count, 0) < COALESCE(ms.match_count, 0) THEN 'Some scheduled matches are still not completed.'
                            END,
                            CASE
                                WHEN COALESCE(fs.pending_finance_event_count, 0) > 0 THEN 'Pending finance events still need reconciliation.'
                            END
                        )
                        ELSE 'Tournament operations are currently on track.'
                    END AS readiness_note
                FROM federation_tournament t
                LEFT JOIN federation_season s ON s.id = t.season_id
                LEFT JOIN participant_stats ps ON ps.tournament_id = t.id
                LEFT JOIN match_stats ms ON ms.tournament_id = t.id
                LEFT JOIN standing_stats ss ON ss.tournament_id = t.id
                LEFT JOIN finance_stats fs ON fs.tournament_id = t.id
                LEFT JOIN club_compliance_stats ccs ON ccs.tournament_id = t.id
            )
            """)
