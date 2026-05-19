from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationClub(models.Model):
    _name = "federation.club"
    _description = "Federation Club"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(string="Club Name", required=True, tracking=True)
    code = fields.Char(string="Code", copy=False, tracking=True)
    active = fields.Boolean(default=True)
    street = fields.Char(string="Street")
    street2 = fields.Char(string="Street 2")
    city = fields.Char(string="City")
    state_id = fields.Many2one("res.country.state", string="State")
    country_id = fields.Many2one("res.country", string="Country")
    zip = fields.Char(string="ZIP")
    email = fields.Char(string="Email", tracking=True)
    phone = fields.Char(string="Phone", tracking=True)
    mobile = fields.Char(string="Mobile")
    website = fields.Char(string="Website")
    founded_date = fields.Date(string="Founded Date")
    logo = fields.Binary(string="Logo")
    notes = fields.Text(string="Notes")

    team_ids = fields.One2many("federation.team", "club_id", string="Teams")
    team_count = fields.Integer(
        string="Team Count", compute="_compute_team_count", store=True
    )

    _code_unique = models.Constraint("unique (code)", "Club code must be unique.")

    @api.depends("team_ids")
    def _compute_team_count(self):
        """Compute team count."""
        for rec in self:
            rec.team_count = len(rec.team_ids)

    def action_view_teams(self):
        """Execute the view teams action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_base.federation_team_action"
        )
        action["domain"] = [("club_id", "=", self.id)]
        return action

    @api.constrains("email")
    def _check_email(self):
        """Validate email."""
        for rec in self:
            if rec.email and "@" not in rec.email:
                raise ValidationError("Invalid email address.")

    def action_archive(self):
        """Execute the archive action."""
        clubs_with_active_teams = self.filtered(
            lambda rec: rec.team_ids.filtered("active")
        )
        if clubs_with_active_teams:
            raise ValidationError(
                _("Archive all active teams before archiving a club.")
            )
        self.write({"active": False})
        return True

    def action_restore(self):
        """Execute the restore action."""
        self.write({"active": True})
        return True
