from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationMatchdaySlotGenerationWizard(models.TransientModel):
    _name = "federation.matchday.slot.generation.wizard"
    _description = "Generate Match-Day Fixture Slots"

    matchday_id = fields.Many2one(
        "federation.matchday",
        required=True,
        readonly=True,
    )
    venue_id = fields.Many2one(related="matchday_id.venue_id", readonly=True)
    court_ids = fields.Many2many(
        "federation.playing.area",
        string="Playing Areas",
        required=True,
        domain="[('venue_id', '=', venue_id), ('active', '=', True)]",
    )
    start_hour = fields.Float(
        string="Game-Day Start",
        required=True,
        default=9.0,
        help="First possible match start in the venue's local game-day window.",
    )
    end_hour = fields.Float(
        string="Game-Day End",
        required=True,
        default=18.0,
        help="Every generated slot must finish by this time.",
    )
    slot_duration_minutes = fields.Integer(
        string="Total Slot Duration",
        required=True,
        default=60,
        help=(
            "Total court occupancy per match. Include regulation play, possible "
            "overtime, post-match clearance, and setup for the next game."
        ),
    )
    noon_pause = fields.Boolean(string="Pause at Noon", default=False)
    noon_pause_minutes = fields.Integer(
        string="Noon Pause Duration",
        default=60,
        help="Pause beginning at 12:00 local game-day time.",
    )
    replace_existing_slots = fields.Boolean(
        string="Replace Existing Slots",
        default=False,
        help="Delete existing draft/capacity slots before generating the new plan.",
    )
    generated_slot_count = fields.Integer(compute="_compute_preview")
    blocked_slot_count = fields.Integer(compute="_compute_preview")
    pause_slot_count = fields.Integer(compute="_compute_preview")

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        matchday = self.env["federation.matchday"].browse(
            self.env.context.get("default_matchday_id")
        )
        if matchday:
            values.update(
                {
                    "matchday_id": matchday.id,
                    "court_ids": [
                        (
                            6,
                            0,
                            matchday.venue_id.playing_area_ids.filtered("active").ids,
                        )
                    ],
                    "start_hour": matchday.default_day_start_hour,
                    "slot_duration_minutes": matchday.default_slot_duration_minutes,
                }
            )
        return values

    @api.depends(
        "matchday_id",
        "court_ids",
        "start_hour",
        "end_hour",
        "slot_duration_minutes",
        "noon_pause",
        "noon_pause_minutes",
    )
    def _compute_preview(self):
        generator = self.env["federation.slot.generator"]
        for wizard in self:
            wizard.generated_slot_count = 0
            wizard.blocked_slot_count = 0
            wizard.pause_slot_count = 0
            if not wizard.matchday_id or not wizard.court_ids:
                continue
            try:
                plan = generator.plan(
                    wizard.matchday_id,
                    wizard.court_ids,
                    wizard.start_hour,
                    wizard.end_hour,
                    wizard.slot_duration_minutes,
                    noon_pause=wizard.noon_pause,
                    noon_pause_minutes=wizard.noon_pause_minutes,
                )
            except ValidationError:
                continue
            wizard.generated_slot_count = len(plan["available"])
            wizard.blocked_slot_count = plan["blocked_count"]
            wizard.pause_slot_count = len(plan["breaks"])

    @api.constrains(
        "start_hour",
        "end_hour",
        "slot_duration_minutes",
        "noon_pause_minutes",
    )
    def _check_generation_parameters(self):
        for wizard in self:
            if not 0 <= wizard.start_hour < 24 or not 0 < wizard.end_hour <= 24:
                raise ValidationError(_("Start and end must be valid times of day."))
            if wizard.end_hour <= wizard.start_hour:
                raise ValidationError(_("Game-day end must be after game-day start."))
            if wizard.slot_duration_minutes <= 0:
                raise ValidationError(_("Total slot duration must be positive."))
            if wizard.noon_pause and wizard.noon_pause_minutes <= 0:
                raise ValidationError(_("Noon pause duration must be positive."))

    def action_generate(self):
        self.ensure_one()
        if self.matchday_id.slot_ids and not self.replace_existing_slots:
            raise ValidationError(
                _(
                    "Existing slots are present. Enable Replace Existing Slots "
                    "to continue."
                )
            )
        self.env["federation.slot.generator"].generate_plan(
            self.matchday_id,
            self.court_ids,
            self.start_hour,
            self.end_hour,
            self.slot_duration_minutes,
            noon_pause=self.noon_pause,
            noon_pause_minutes=self.noon_pause_minutes,
            replace_existing=self.replace_existing_slots,
        )
        return {"type": "ir.actions.client", "tag": "reload"}
