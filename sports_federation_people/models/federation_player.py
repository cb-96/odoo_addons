from odoo import api, fields, models
from odoo.exceptions import ValidationError
from datetime import date


class FederationPlayer(models.Model):
    _name = "federation.player"
    _description = "Federation Player"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "last_name, first_name"

    name = fields.Char(string="Full Name", compute="_compute_name", store=True)
    first_name = fields.Char(string="First Name", required=True, tracking=True)
    last_name = fields.Char(string="Last Name", required=True, tracking=True)
    birth_date = fields.Date(string="Date of Birth", tracking=True)
    gender = fields.Selection(
        [("male", "Male"), ("female", "Female")],
        string="Gender",
        tracking=True,
    )
    nationality_id = fields.Many2one(
        "res.country", string="Nationality", ondelete="set null"
    )
    active = fields.Boolean(default=True)
    state = fields.Selection(
        [
            ("active", "Active"),
            ("inactive", "Inactive"),
            ("suspended", "Suspended"),
        ],
        string="Status",
        default="active",
        required=True,
        tracking=True,
    )
    club_id = fields.Many2one(
        "federation.club", string="Current Club", tracking=True, ondelete="set null"
    )
    team_ids = fields.Many2many(
        "federation.team", string="Teams", relation="federation_player_team_rel"
    )
    email = fields.Char(string="Email")
    phone = fields.Char(string="Phone")
    mobile = fields.Char(string="Mobile")
    photo = fields.Binary(string="Photo")
    notes = fields.Text(string="Notes")

    license_ids = fields.One2many(
        "federation.player.license", "player_id", string="Licenses"
    )
    license_count = fields.Integer(
        string="License Count", compute="_compute_counts", store=True
    )
    is_eligible = fields.Boolean(
        string="Eligible",
        compute="_compute_is_eligible",
        help="True if the player has at least one active license.",
    )

    _name_birthdate_unique = models.Constraint(
        "unique (first_name, last_name, birth_date)",
        "A player with the same name and birth date already exists.",
    )

    @api.depends("first_name", "last_name")
    def _compute_name(self):
        """Compute name."""
        for rec in self:
            parts = [p for p in [rec.first_name, rec.last_name] if p]
            rec.name = " ".join(parts) or "New"

    @api.depends("license_ids")
    def _compute_counts(self):
        """Compute counts."""
        for rec in self:
            rec.license_count = len(rec.license_ids)

    @api.depends("license_ids.state")
    def _compute_is_eligible(self):
        """Compute eligibility: True if the player has at least one active license."""
        for rec in self:
            rec.is_eligible = any(lic.state == "active" for lic in rec.license_ids)

    def action_view_licenses(self):
        """Execute the view licenses action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_people.federation_player_license_action"
        )
        action["domain"] = [("player_id", "=", self.id)]
        return action

    @api.constrains("birth_date")
    def _check_birth_date(self):
        """Validate birth date."""
        for rec in self:
            if rec.birth_date and rec.birth_date > date.today():
                raise ValidationError("Date of birth cannot be in the future.")

    def action_activate(self):
        """Execute the activate action."""
        for rec in self:
            rec.state = "active"

    def action_deactivate(self):
        """Execute the deactivate action."""
        for rec in self:
            rec.state = "inactive"

    def action_suspend(self):
        """Execute the suspend action."""
        for rec in self:
            rec.state = "suspended"

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        """Search records by their display-name components."""
        args = args or []
        if name:
            domain = [
                "|",
                ("first_name", operator, name),
                ("last_name", operator, name),
            ]
            recs = self.search(domain + args, limit=limit)
            return (
                recs.name_get()
                if hasattr(recs, "name_get")
                else [(r.id, r.display_name) for r in recs]
            )
        return super().name_search(name, args, operator, limit)
