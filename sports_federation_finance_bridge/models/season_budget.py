from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationSeasonBudget(models.Model):
    _name = "federation.season.budget"
    _description = "Federation Season Budget"
    _order = "season_id desc, fee_type_id"

    name = fields.Char(string="Name", compute="_compute_name", store=True)
    season_id = fields.Many2one(
        "federation.season",
        required=True,
        ondelete="cascade",
        index=True,
    )
    fee_type_id = fields.Many2one(
        "federation.fee.type",
        required=True,
        ondelete="restrict",
        index=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="fee_type_id.currency_id",
        readonly=True,
        store=True,
    )
    budget_amount = fields.Monetary(currency_field="currency_id", required=True)
    actual_amount = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_actual_metrics",
        readonly=True,
    )
    actual_event_count = fields.Integer(
        compute="_compute_actual_metrics", readonly=True
    )
    variance_amount = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_actual_metrics",
        readonly=True,
    )
    variance_pct = fields.Float(
        compute="_compute_actual_metrics", readonly=True, digits=(16, 2)
    )
    notes = fields.Text()

    _season_fee_unique = models.Constraint(
        "UNIQUE(season_id, fee_type_id)",
        "A budget already exists for this season and fee type.",
    )

    @api.depends("season_id", "fee_type_id")
    def _compute_name(self):
        """Compute name."""
        for record in self:
            season_name = record.season_id.display_name or "Season"
            fee_name = record.fee_type_id.display_name or "Budget"
            record.name = f"{season_name} - {fee_name}"

    @api.depends("season_id", "fee_type_id", "budget_amount")
    def _compute_actual_metrics(self):
        """Compute actual metrics."""
        metrics = {}
        season_ids = self.mapped("season_id").ids
        fee_type_ids = self.mapped("fee_type_id").ids
        if season_ids and fee_type_ids:
            finance_events = self.env["federation.finance.event"].search(
                [
                    ("season_id", "in", season_ids),
                    ("fee_type_id", "in", fee_type_ids),
                    ("state", "in", ("confirmed", "settled")),
                ]
            )
            for event in finance_events:
                key = (event.season_id.id, event.fee_type_id.id)
                metric = metrics.setdefault(key, {"amount": 0.0, "count": 0})
                metric["amount"] += event.amount or 0.0
                metric["count"] += 1

        for record in self:
            metric = metrics.get((record.season_id.id, record.fee_type_id.id), {})
            actual_amount = metric.get("amount", 0.0)
            record.actual_amount = actual_amount
            record.actual_event_count = metric.get("count", 0)
            record.variance_amount = actual_amount - (record.budget_amount or 0.0)
            if record.budget_amount:
                record.variance_pct = (
                    record.variance_amount / record.budget_amount
                ) * 100
            else:
                record.variance_pct = 0.0

    @api.constrains("budget_amount")
    def _check_budget_amount(self):
        """Validate budget amount."""
        for record in self:
            if record.budget_amount < 0:
                raise ValidationError("Budget amounts must be zero or greater.")

    def action_view_finance_events(self):
        """Execute the view finance events action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_finance_bridge.action_federation_finance_event"
        )
        action["domain"] = [
            ("season_id", "=", self.season_id.id),
            ("fee_type_id", "=", self.fee_type_id.id),
        ]
        return action
