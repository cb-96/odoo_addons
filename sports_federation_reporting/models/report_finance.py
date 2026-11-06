from odoo import fields, models


class FederationReportFinance(models.Model):
    _name = "federation.report.finance"
    _description = "Federation Finance Report"
    _auto = False
    _order = "fee_type_id, state"

    company_id = fields.Many2one("res.company", readonly=True)
    currency_id = fields.Many2one("res.currency", readonly=True)
    fee_type_id = fields.Many2one(
        "federation.fee.type", string="Fee Type", readonly=True
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("settled", "Settled"),
            ("cancelled", "Cancelled"),
        ],
        string="State",
        readonly=True,
    )
    event_count = fields.Integer(string="Events", readonly=True)
    total_amount = fields.Float(string="Total Amount", readonly=True)

    def init(self):
        """Create SQL view for finance report."""
        self.env["federation.report.sql.helper"].recreate_view(
            self._table,
            """
            CREATE VIEW federation_report_finance AS (
                SELECT
                    MIN(fe.id) AS id,
                    fe.company_id,
                    fe.currency_id,
                    fe.fee_type_id,
                    fe.state,
                    COUNT(DISTINCT fe.id) AS event_count,
                    SUM(fe.amount) AS total_amount
                FROM federation_finance_event fe
                GROUP BY fe.company_id, fe.currency_id, fe.fee_type_id, fe.state
            )
            """,
        )
