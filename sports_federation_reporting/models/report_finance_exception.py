from odoo import fields, models, tools


class FederationReportFinanceException(models.Model):
    _name = "federation.report.finance.exception"
    _description = "Federation Finance Exception Report"
    _auto = False
    _order = "effective_date desc, sanction_id desc"

    ISSUE_TYPE_SELECTION = [
        ("missing_fine_event", "Missing Fine Event"),
    ]

    sanction_id = fields.Many2one(
        "federation.sanction", string="Sanction", readonly=True
    )
    case_id = fields.Many2one(
        "federation.disciplinary.case",
        string="Case",
        readonly=True,
    )
    case_reference = fields.Char(string="Case Reference", readonly=True)
    player_id = fields.Many2one("federation.player", string="Player", readonly=True)
    club_id = fields.Many2one("federation.club", string="Club", readonly=True)
    referee_id = fields.Many2one("federation.referee", string="Referee", readonly=True)
    expected_fee_type_id = fields.Many2one(
        "federation.fee.type",
        string="Expected Fee Type",
        readonly=True,
    )
    effective_date = fields.Date(string="Effective Date", readonly=True)
    expected_amount = fields.Monetary(
        string="Expected Amount",
        currency_field="currency_id",
        readonly=True,
    )
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    issue_type = fields.Selection(
        ISSUE_TYPE_SELECTION, string="Issue Type", readonly=True
    )
    issue_note = fields.Text(string="Issue Note", readonly=True)

    def init(self):
        """Rebuild the SQL view so sanction exception fields match the query output."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_finance_exception AS (
                -- block: discipline_fee
                WITH discipline_fee AS (
                    SELECT id, default_amount
                    FROM federation_fee_type
                    WHERE code = 'discipline_fine'
                    LIMIT 1
                )
                -- block: report_rows
                SELECT
                    row_number() OVER (
                        ORDER BY COALESCE(s.effective_date, c.decided_on, c.opened_on) DESC, s.id DESC
                    ) AS id,
                    s.id AS sanction_id,
                    s.case_id,
                    c.reference AS case_reference,
                    COALESCE(s.player_id, c.subject_player_id) AS player_id,
                    COALESCE(s.club_id, c.subject_club_id) AS club_id,
                    COALESCE(s.referee_id, c.subject_referee_id) AS referee_id,
                    df.id AS expected_fee_type_id,
                    COALESCE(s.effective_date, c.decided_on, c.opened_on) AS effective_date,
                    CASE
                        WHEN COALESCE(s.amount, 0) = 0 THEN COALESCE(df.default_amount, 0)
                        ELSE s.amount
                    END AS expected_amount,
                    s.currency_id,
                    'missing_fine_event' AS issue_type,
                    'Fine sanction has no linked finance event.' AS issue_note
                FROM federation_sanction s
                JOIN federation_disciplinary_case c ON c.id = s.case_id
                LEFT JOIN discipline_fee df ON TRUE
                LEFT JOIN federation_finance_event fe
                  ON fe.source_model = 'federation.sanction'
                 AND fe.source_res_id = s.id
                 AND (df.id IS NULL OR fe.fee_type_id = df.id)
                WHERE s.sanction_type = 'fine'
                  AND fe.id IS NULL
            )
            """)
