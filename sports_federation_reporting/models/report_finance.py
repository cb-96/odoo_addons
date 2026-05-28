from odoo import fields, models, tools


class FederationReportFinance(models.Model):
    _name = "federation.report.finance"
    _description = "Federation Finance Report"
    _auto = False
    _order = "fee_type_id, state"

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
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_finance AS (
                SELECT
                    row_number() OVER () AS id,
                    fe.fee_type_id,
                    fe.state,
                    COUNT(DISTINCT fe.id) AS event_count,
                    SUM(fe.amount) AS total_amount
                FROM federation_finance_event fe
                GROUP BY fe.fee_type_id, fe.state
            )
        """)
