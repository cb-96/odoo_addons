from odoo import fields, models, tools

from .report_operational import FederationReportOperational


class FederationReportFinanceReconciliation(models.Model):
    _name = "federation.report.finance.reconciliation"
    _description = "Federation Finance Reconciliation Report"
    _auto = False
    _order = "needs_follow_up desc, created_on desc"

    EVENT_TYPE_SELECTION = [
        ("charge", "Charge"),
        ("credit", "Credit"),
        ("reimbursement", "Reimbursement"),
    ]
    STATE_SELECTION = [
        ("draft", "Draft"),
        ("confirmed", "Confirmed"),
        ("settled", "Settled"),
        ("cancelled", "Cancelled"),
    ]
    FOLLOW_UP_SELECTION = [
        ("draft", "Draft"),
        ("awaiting_settlement", "Awaiting Settlement"),
        ("awaiting_reference", "Awaiting Reference"),
        ("complete", "Complete"),
        ("cancelled", "Cancelled"),
    ]

    finance_event_id = fields.Many2one(
        "federation.finance.event", string="Finance Event", readonly=True
    )
    fee_type_id = fields.Many2one(
        "federation.fee.type", string="Fee Type", readonly=True
    )
    event_type = fields.Selection(
        EVENT_TYPE_SELECTION, string="Event Type", readonly=True
    )
    state = fields.Selection(STATE_SELECTION, string="State", readonly=True)
    created_on = fields.Datetime(string="Created On", readonly=True)
    club_id = fields.Many2one("federation.club", string="Club", readonly=True)
    player_id = fields.Many2one("federation.player", string="Player", readonly=True)
    referee_id = fields.Many2one("federation.referee", string="Referee", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Partner", readonly=True)
    counterparty_display = fields.Char(string="Counterparty", readonly=True)
    source_model = fields.Char(string="Source Model", readonly=True)
    source_res_id = fields.Integer(string="Source Record ID", readonly=True)
    currency_id = fields.Many2one("res.currency", string="Currency", readonly=True)
    amount = fields.Monetary(
        string="Amount", currency_field="currency_id", readonly=True
    )
    invoice_ref = fields.Char(string="Invoice Ref", readonly=True)
    external_ref = fields.Char(string="External Ref", readonly=True)
    age_days = fields.Integer(string="Age (Days)", readonly=True)
    queue_owner_display = fields.Char(string="Queue Owner", readonly=True)
    sla_due_on = fields.Datetime(string="SLA Due On", readonly=True)
    sla_status = fields.Selection(
        FederationReportOperational.SLA_STATUS_SELECTION,
        string="SLA Status",
        readonly=True,
    )
    follow_up_status = fields.Selection(
        FOLLOW_UP_SELECTION, string="Follow-up Status", readonly=True
    )
    needs_follow_up = fields.Boolean(string="Needs Follow-up", readonly=True)

    def init(self):
        """Rebuild the SQL view so queue fields match the finance follow-up query."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_finance_reconciliation AS (
                -- block: report_rows
                SELECT
                    fe.id AS id,
                    fe.id AS finance_event_id,
                    fe.fee_type_id,
                    fe.event_type,
                    fe.state,
                    fe.create_date AS created_on,
                    fe.club_id,
                    fe.player_id,
                    fe.referee_id,
                    fe.partner_id,
                    COALESCE(fc.name, fp.name, fr.name, rp.name, '') AS counterparty_display,
                    fe.source_model,
                    fe.source_res_id,
                    fe.currency_id,
                    fe.amount,
                    fe.invoice_ref,
                    fe.external_ref,
                    (CURRENT_DATE - COALESCE(fe.create_date::date, CURRENT_DATE))::int AS age_days,
                    'Federation Managers'::varchar AS queue_owner_display,
                    (COALESCE(fe.create_date, NOW()) + INTERVAL '2 day') AS sla_due_on,
                    CASE
                        WHEN fe.state = 'cancelled' THEN 'cancelled'
                        WHEN fe.state = 'settled'
                            AND COALESCE(NULLIF(fe.invoice_ref, ''), NULLIF(fe.external_ref, '')) IS NOT NULL THEN 'complete'
                        WHEN CURRENT_TIMESTAMP < (COALESCE(fe.create_date, NOW()) + INTERVAL '2 day') THEN 'within_sla'
                        WHEN CURRENT_DATE = (COALESCE(fe.create_date, NOW()) + INTERVAL '2 day')::date THEN 'due_today'
                        WHEN CURRENT_TIMESTAMP < (COALESCE(fe.create_date, NOW()) + INTERVAL '5 day') THEN 'overdue'
                        ELSE 'escalated'
                    END AS sla_status,
                    CASE
                        WHEN fe.state = 'cancelled' THEN 'cancelled'
                        WHEN fe.state = 'settled'
                          AND COALESCE(NULLIF(fe.invoice_ref, ''), NULLIF(fe.external_ref, '')) IS NULL THEN 'awaiting_reference'
                        WHEN fe.state = 'settled' THEN 'complete'
                        WHEN fe.state = 'confirmed' THEN 'awaiting_settlement'
                        ELSE 'draft'
                    END AS follow_up_status,
                    CASE
                        WHEN fe.state IN ('draft', 'confirmed') THEN TRUE
                        WHEN fe.state = 'settled'
                          AND COALESCE(NULLIF(fe.invoice_ref, ''), NULLIF(fe.external_ref, '')) IS NULL THEN TRUE
                        ELSE FALSE
                    END AS needs_follow_up
                FROM federation_finance_event fe
                LEFT JOIN federation_club fc ON fc.id = fe.club_id
                LEFT JOIN federation_player fp ON fp.id = fe.player_id
                LEFT JOIN federation_referee fr ON fr.id = fe.referee_id
                LEFT JOIN res_partner rp ON rp.id = fe.partner_id
            )
            """)
