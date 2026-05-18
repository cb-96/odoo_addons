from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationFeeSchedule(models.Model):
    _name = "federation.fee.schedule"
    _description = "Federation Fee Schedule"
    _order = "season_id desc, fee_type_id, category, gender"

    season_id = fields.Many2one(
        "federation.season",
        required=True,
        ondelete="cascade",
        index=True,
    )
    fee_type_id = fields.Many2one(
        "federation.fee.type",
        required=True,
        ondelete="cascade",
    )
    category = fields.Selection(
        [
            ("senior", "Senior"),
            ("youth", "Youth"),
            ("junior", "Junior"),
            ("cadet", "Cadet"),
            ("mini", "Mini"),
        ],
        required=True,
    )
    gender = fields.Selection(
        [("male", "Male"), ("female", "Female"), ("mixed", "Mixed")],
        required=True,
    )
    amount = fields.Monetary(currency_field="currency_id", required=True)
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    notes = fields.Text()

    _schedule_unique = models.Constraint(
        "UNIQUE(season_id, fee_type_id, category, gender)",
        "A fee schedule entry already exists for this season, fee type, category and gender.",
    )

    @api.constrains("amount")
    def _check_amount(self):
        for record in self:
            if record.amount < 0:
                raise ValidationError("Fee schedule amount must be >= 0.")

    @api.model
    def lookup_amount(self, fee_type, season, category, gender):
        """Return scheduled amount for the given combination, or False if none."""
        if not (fee_type and season and category and gender):
            return False
        schedule = self.search(
            [
                ("fee_type_id", "=", fee_type.id),
                ("season_id", "=", season.id),
                ("category", "=", category),
                ("gender", "=", gender),
            ],
            limit=1,
        )
        if schedule:
            return schedule.amount
        return False
