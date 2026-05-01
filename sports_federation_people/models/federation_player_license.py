from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationPlayerLicense(models.Model):
    _name = "federation.player.license"
    _description = "Player License"
    _order = "issue_date desc, id"

    name = fields.Char(string="License Number", required=True, copy=False)
    player_id = fields.Many2one(
        "federation.player", string="Player", required=True, ondelete="cascade"
    )
    season_id = fields.Many2one(
        "federation.season", string="Season", required=True, ondelete="restrict"
    )
    club_id = fields.Many2one(
        "federation.club", string="Club", required=True, ondelete="restrict"
    )
    issue_date = fields.Date(
        string="Issue Date", required=True, default=fields.Date.context_today
    )
    expiry_date = fields.Date(string="Expiry Date", required=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
    )
    category = fields.Selection(
        [
            ("senior", "Senior"),
            ("youth", "Youth"),
            ("junior", "Junior"),
            ("cadet", "Cadet"),
        ],
        string="Category",
    )
    eligibility_notes = fields.Text(string="Eligibility Notes")
    notes = fields.Text(string="Notes")

    _player_season_unique = models.Constraint(
        "unique (player_id, season_id)",
        "A player can only have one license per season.",
    )

    @api.constrains("issue_date", "expiry_date")
    def _check_dates(self):
        """Validate dates."""
        for rec in self:
            if rec.issue_date and rec.expiry_date and rec.expiry_date <= rec.issue_date:
                raise ValidationError("Expiry date must be after issue date.")

    def action_activate(self):
        """Execute the activate action."""
        for rec in self:
            rec.state = "active"

    def action_cancel(self):
        """Execute the cancel action."""
        for rec in self:
            rec.state = "cancelled"

    def action_draft(self):
        """Execute the draft action."""
        for rec in self:
            rec.state = "draft"
