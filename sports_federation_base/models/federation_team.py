from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationTeam(models.Model):
    _name = "federation.team"
    _description = "Federation Team"
    _inherit = ["mail.thread"]
    _order = "name"

    name = fields.Char(string="Team Name", required=True, tracking=True)
    code = fields.Char(string="Code", copy=False)
    active = fields.Boolean(default=True)
    club_id = fields.Many2one(
        "federation.club",
        string="Club",
        required=True,
        tracking=True,
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
        string="Category",
        default="senior",
        tracking=True,
    )
    gender = fields.Selection(
        [("male", "Male"), ("female", "Female"), ("mixed", "Mixed")],
        string="Gender",
        default="male",
    )
    email = fields.Char(string="Email")
    phone = fields.Char(string="Phone")
    logo = fields.Binary(string="Logo")
    notes = fields.Text(string="Notes")

    registration_ids = fields.One2many(
        "federation.season.registration", "team_id", string="Registrations"
    )
    registration_count = fields.Integer(
        string="Registration Count", compute="_compute_registration_count", store=True
    )

    _code_unique = models.Constraint("unique (code)", "Team code must be unique.")

    @api.depends("name", "gender")
    def _compute_display_name(self):
        """Compute display name."""
        gender_labels = {
            "male": _("Men"),
            "female": _("Women"),
            "mixed": _("Mixed"),
        }
        for rec in self:
            base_name = rec.name or _("New")
            gender_label = gender_labels.get(rec.gender)
            rec.display_name = (
                "%s (%s)" % (base_name, gender_label) if gender_label else base_name
            )

    @api.depends("registration_ids")
    def _compute_registration_count(self):
        """Compute registration count."""
        for rec in self:
            rec.registration_count = len(rec.registration_ids)

    def action_view_registrations(self):
        """Execute the view registrations action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_base.federation_season_registration_action"
        )
        action["domain"] = [("team_id", "=", self.id)]
        return action

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        """Search records by their display-name components."""
        args = args or []
        if name:
            domain = ["|", ("name", operator, name), ("code", operator, name)]
            recs = self.search(domain + args, limit=limit)
            return (
                recs.name_get()
                if hasattr(recs, "name_get")
                else [(r.id, r.display_name) for r in recs]
            )
        return super().name_search(name, args, operator, limit)

    def action_archive(self):
        """Execute the archive action."""
        teams_with_active_registrations = self.filtered(
            lambda rec: rec.registration_ids.filtered(
                lambda registration: registration.state != "cancelled"
            )
        )
        if teams_with_active_registrations:
            raise ValidationError(
                _(
                    "Cancel or complete the team's active season registrations before archiving it."
                )
            )
        self.write({"active": False})
        return True

    def action_restore(self):
        """Execute the restore action."""
        self.write({"active": True})
        return True
