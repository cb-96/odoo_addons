from odoo import api, fields, models


class FederationVenue(models.Model):
    _name = "federation.venue"
    _description = "Federation Venue"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    street = fields.Char()
    street2 = fields.Char()
    zip = fields.Char()
    city = fields.Char()
    country_id = fields.Many2one("res.country")
    contact_name = fields.Char()
    contact_email = fields.Char()
    contact_phone = fields.Char()
    capacity = fields.Integer()
    equipment_notes = fields.Text()
    notes = fields.Text()
    playing_area_ids = fields.One2many(
        "federation.playing.area", "venue_id", string="Playing Areas"
    )
    playing_area_count = fields.Integer(
        compute="_compute_playing_area_count",
        string="Playing Area Count",
    )

    _unique_name_city = models.Constraint(
        "UNIQUE(name, city)",
        "A venue with this name already exists in this city.",
    )

    @api.depends("playing_area_ids")
    def _compute_playing_area_count(self):
        """Compute playing area count."""
        for record in self:
            record.playing_area_count = len(record.playing_area_ids)

    def action_view_playing_areas(self):
        """Execute the view playing areas action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_venues.action_federation_playing_area"
        )
        action["domain"] = [("venue_id", "=", self.id)]
        return action


class FederationPlayingArea(models.Model):
    _name = "federation.playing.area"
    _description = "Federation Playing Area"

    name = fields.Char(required=True)
    venue_id = fields.Many2one(
        "federation.venue",
        required=True,
        ondelete="cascade",
        index=True,
    )
    code = fields.Char()
    capacity = fields.Integer()
    surface_type = fields.Selection(
        [
            ("indoor", "Indoor"),
            ("outdoor", "Outdoor"),
            ("other", "Other"),
        ],
        default="indoor",
    )
    notes = fields.Text()
    active = fields.Boolean(default=True)

    _unique_venue_name = models.Constraint(
        "UNIQUE(venue_id, name)",
        "A playing area with this name already exists for this venue.",
    )
