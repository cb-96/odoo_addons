from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

SLOT_STATE_SELECTION = [
    ("available", "Available"),
    ("reserved", "Reserved"),
    ("assigned", "Assigned"),
    ("blocked", "Blocked"),
    ("break", "Break"),
    ("cancelled", "Cancelled"),
]


class FederationMatchSlot(models.Model):
    _name = "federation.match.slot"
    _description = "Federation Match Slot"
    _order = "start_datetime, playing_area_id, id"

    name = fields.Char(
        string="Slot",
        compute="_compute_name",
        store=True,
    )
    sequence = fields.Integer(string="Sequence", default=10)
    round_id = fields.Many2one(
        "federation.tournament.round",
        string="Gameday",
        required=True,
        ondelete="cascade",
        index=True,
    )
    tournament_id = fields.Many2one(
        related="round_id.tournament_id",
        store=True,
        readonly=True,
    )
    stage_id = fields.Many2one(
        related="round_id.stage_id",
        store=True,
        readonly=True,
    )
    edition_id = fields.Many2one(
        related="tournament_id.edition_id",
        store=True,
        readonly=True,
    )
    venue_id = fields.Many2one(
        "federation.venue",
        string="Venue",
        required=True,
        ondelete="restrict",
    )
    playing_area_id = fields.Many2one(
        "federation.playing.area",
        string="Court",
        required=True,
        ondelete="restrict",
        domain="[('venue_id', '=', venue_id)]",
    )
    start_datetime = fields.Datetime(string="Start", required=True, index=True)
    end_datetime = fields.Datetime(string="End", required=True, index=True)
    match_id = fields.Many2one(
        "federation.match",
        string="Assigned Match",
        ondelete="set null",
        copy=False,
    )
    state = fields.Selection(
        SLOT_STATE_SELECTION,
        string="State",
        default="available",
        required=True,
    )
    note = fields.Char(string="Note")

    _slot_unique_match = models.Constraint(
        "UNIQUE(match_id)",
        "A match can only be assigned to one planner slot at a time.",
    )
    _slot_unique_start = models.Constraint(
        "UNIQUE(round_id, playing_area_id, start_datetime)",
        "A court can only have one slot starting at the same time on the same gameday.",
    )
    _slot_positive_duration = models.Constraint(
        "CHECK(end_datetime > start_datetime)",
        "A planner slot must end after it starts.",
    )

    @api.depends("playing_area_id", "start_datetime", "end_datetime")
    def _compute_name(self):
        for record in self:
            if not record.start_datetime or not record.end_datetime:
                record.name = record.playing_area_id.display_name or _("New slot")
                continue
            start_label = fields.Datetime.to_datetime(record.start_datetime).strftime(
                "%H:%M"
            )
            end_label = fields.Datetime.to_datetime(record.end_datetime).strftime(
                "%H:%M"
            )
            area_label = record.playing_area_id.display_name or _("Court")
            record.name = _("%(court)s %(start)s-%(end)s") % {
                "court": area_label,
                "start": start_label,
                "end": end_label,
            }

    @api.constrains("venue_id", "playing_area_id")
    def _check_playing_area_scope(self):
        """Keep slot venue and court selection aligned."""
        for record in self.filtered("playing_area_id"):
            if record.playing_area_id.venue_id != record.venue_id:
                raise ValidationError(
                    _("The selected court must belong to the selected venue.")
                )

    @api.constrains("state", "match_id")
    def _check_assignment_state(self):
        """Prevent blocked or break slots from carrying matches."""
        forbidden_states = {"blocked", "break", "cancelled"}
        for record in self.filtered("match_id"):
            if record.state in forbidden_states:
                raise ValidationError(
                    _(
                        "Blocked, break, or cancelled slots cannot carry an assigned match."
                    )
                )

    @api.onchange("playing_area_id")
    def _onchange_playing_area_id(self):
        """Keep venue aligned when the planner court changes in the form view."""
        if self.playing_area_id and not self.venue_id:
            self.venue_id = self.playing_area_id.venue_id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_assignment_state()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._sync_assignment_state()
        return result

    def _sync_assignment_state(self):
        """Keep the slot state aligned with whether it carries a match."""
        for record in self:
            if record.match_id and record.state in {"available", "reserved", "assigned"}:
                super(FederationMatchSlot, record).write({"state": "assigned"})
            elif not record.match_id and record.state == "assigned":
                super(FederationMatchSlot, record).write({"state": "available"})