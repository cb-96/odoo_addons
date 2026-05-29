from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
    blackout_window_ids = fields.One2many(
        "federation.venue.blackout", "venue_id", string="Constraint Windows"
    )
    playing_area_count = fields.Integer(
        compute="_compute_playing_area_count",
        string="Playing Area Count",
    )
    blackout_window_count = fields.Integer(
        compute="_compute_playing_area_count",
        string="Constraint Window Count",
    )

    _unique_name_city = models.Constraint(
        "UNIQUE(name, city)",
        "A venue with this name already exists in this city.",
    )

    @api.depends("playing_area_ids", "blackout_window_ids")
    def _compute_playing_area_count(self):
        """Compute playing area count."""
        for record in self:
            record.playing_area_count = len(record.playing_area_ids)
            record.blackout_window_count = len(record.blackout_window_ids)

    def action_view_playing_areas(self):
        """Execute the view playing areas action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_venues.action_federation_playing_area"
        )
        action["domain"] = [("venue_id", "=", self.id)]
        return action

    def action_view_blackout_windows(self):
        """Open venue blackout and maintenance windows."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_venues.action_federation_venue_blackout"
        )
        action["domain"] = [("venue_id", "=", self.id)]
        action["context"] = {"default_venue_id": self.id}
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
    capability_ids = fields.Many2many(
        "federation.playing.area.capability",
        "federation_playing_area_capability_rel",
        "playing_area_id",
        "capability_id",
        string="Capabilities",
    )
    notes = fields.Text()
    active = fields.Boolean(default=True)

    _unique_venue_name = models.Constraint(
        "UNIQUE(venue_id, name)",
        "A playing area with this name already exists for this venue.",
    )


class FederationPlayingAreaCapability(models.Model):
    _name = "federation.playing.area.capability"
    _description = "Playing Area Capability"

    name = fields.Char(required=True)
    code = fields.Char()
    description = fields.Text()
    active = fields.Boolean(default=True)

    _unique_code = models.Constraint(
        "UNIQUE(code)",
        "A playing-area capability already uses this code.",
    )


class FederationVenueBlackout(models.Model):
    _name = "federation.venue.blackout"
    _description = "Venue Constraint Window"
    _order = "date_start, id"

    name = fields.Char(compute="_compute_name", store=True)
    venue_id = fields.Many2one(
        "federation.venue",
        required=True,
        ondelete="cascade",
        index=True,
    )
    playing_area_id = fields.Many2one(
        "federation.playing.area",
        string="Playing Area",
        domain='[("venue_id", "=", venue_id)]',
        ondelete="cascade",
    )
    date_start = fields.Datetime(required=True, index=True)
    date_end = fields.Datetime(required=True, index=True)
    closure_type = fields.Selection(
        [
            ("blackout", "Blackout"),
            ("maintenance", "Maintenance"),
        ],
        required=True,
        default="blackout",
    )
    note = fields.Text()
    active = fields.Boolean(default=True)

    @api.depends(
        "venue_id", "playing_area_id", "date_start", "date_end", "closure_type"
    )
    def _compute_name(self):
        for record in self:
            if not record.date_start or not record.date_end:
                record.name = (
                    record.playing_area_id.display_name or record.venue_id.display_name
                )
                continue
            area_label = (
                record.playing_area_id.display_name or record.venue_id.display_name
            )
            window_label = _(
                "%(start)s to %(end)s",
                start=fields.Datetime.to_datetime(record.date_start).strftime(
                    "%Y-%m-%d %H:%M"
                ),
                end=fields.Datetime.to_datetime(record.date_end).strftime(
                    "%Y-%m-%d %H:%M"
                ),
            )
            record.name = _(
                "%(type)s: %(area)s (%(window)s)",
                type=dict(self._fields["closure_type"].selection).get(
                    record.closure_type
                ),
                area=area_label,
                window=window_label,
            )

    @api.constrains("date_start", "date_end", "playing_area_id", "venue_id")
    def _check_window(self):
        for record in self:
            if record.date_end <= record.date_start:
                raise ValidationError(
                    _("A venue constraint window must end after it starts.")
                )
            if (
                record.playing_area_id
                and record.playing_area_id.venue_id != record.venue_id
            ):
                raise ValidationError(
                    _("The selected playing area must belong to the chosen venue.")
                )
