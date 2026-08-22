from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationMatchday(models.Model):
    _name = "federation.matchday"
    _description = "Physical Competition Match Day"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date,id"
    name = fields.Char(required=True)
    edition_id = fields.Many2one(
        "federation.competition.edition", required=True, ondelete="cascade", index=True
    )
    date = fields.Date(required=True, index=True)
    venue_id = fields.Many2one(
        "federation.venue", required=True, ondelete="restrict", index=True
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("capacity_ready", "Capacity Ready"),
            ("scheduled", "Scheduled"),
            ("open", "Open"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    allocation_ids = fields.One2many("federation.matchday.allocation", "matchday_id")
    slot_ids = fields.One2many("federation.schedule.slot", "matchday_id")
    fixture_count = fields.Integer(compute="_compute_capacity")
    playable_slot_count = fields.Integer(compute="_compute_capacity")
    spare_capacity = fields.Integer(compute="_compute_capacity")
    default_day_start_hour = fields.Float(
        string="Default slot start",
        default=9.0,
        required=True,
        help="Local start time used for the first slot on a court.",
    )
    default_slot_duration_minutes = fields.Integer(
        string="Default slot duration",
        default=40,
        required=True,
        help="Duration proposed for a new slot when no previous slot duration is available.",
    )

    @api.constrains("default_day_start_hour", "default_slot_duration_minutes")
    def _check_slot_defaults(self):
        for rec in self:
            if rec.default_day_start_hour < 0 or rec.default_day_start_hour >= 24:
                raise ValidationError(
                    _("The default slot start must be between 00:00 and 23:59.")
                )
            if rec.default_slot_duration_minutes <= 0:
                raise ValidationError(_("The default slot duration must be positive."))

    @api.depends("allocation_ids.fixture_ids", "slot_ids.state")
    def _compute_capacity(self):
        for r in self:
            r.fixture_count = len(r.allocation_ids.mapped("fixture_ids"))
            r.playable_slot_count = len(
                r.slot_ids.filtered(lambda s: s.state == "available")
            )
            r.spare_capacity = r.playable_slot_count - r.fixture_count

    def action_capacity_ready(self):
        for r in self:
            if not r.slot_ids.filtered(lambda s: s.state == "available"):
                raise ValidationError("Generate playable slots first.")
            if not r.allocation_ids:
                raise ValidationError("Allocate fixtures or rounds first.")
            r.state = "capacity_ready"
        return True


class FederationMatchdayAllocation(models.Model):
    _name = "federation.matchday.allocation"
    _description = "Match-Day Fixture Allocation"
    matchday_id = fields.Many2one(
        "federation.matchday", required=True, ondelete="cascade", index=True
    )
    structure_id = fields.Many2one(
        "federation.competition.structure",
        required=True,
        ondelete="restrict",
        index=True,
    )
    stage_id = fields.Many2one(
        "federation.structure.stage", ondelete="restrict", index=True
    )
    round_number = fields.Integer(index=True)
    fixture_ids = fields.Many2many("federation.fixture", compute="_compute_fixtures")

    @api.depends("structure_id", "stage_id", "round_number")
    def _compute_fixtures(self):
        Fixture = self.env["federation.fixture"]
        for r in self:
            domain = (
                [("structure_id", "=", r.structure_id.id)]
                if r.structure_id
                else [("id", "=", False)]
            )
            if r.stage_id:
                domain.append(("stage_id", "=", r.stage_id.id))
            if r.round_number:
                domain.append(("round_number", "=", r.round_number))
            r.fixture_ids = Fixture.search(domain)


class FederationScheduleSlot(models.Model):
    _name = "federation.schedule.slot"
    _description = "Physical Schedule Slot"
    _order = "start_datetime,court_id,id"
    matchday_id = fields.Many2one(
        "federation.matchday", required=True, ondelete="cascade", index=True
    )
    court_id = fields.Many2one(
        "federation.playing.area", required=True, ondelete="restrict", index=True
    )
    start_datetime = fields.Datetime(required=True, index=True)
    end_datetime = fields.Datetime(required=True, index=True)
    state = fields.Selection(
        [("available", "Available"), ("break", "Break"), ("blocked", "Blocked")],
        default="available",
        required=True,
        index=True,
    )
    note = fields.Char()

    @api.model
    def default_get(self, field_list):
        values = super().default_get(field_list)
        matchday_id = values.get("matchday_id") or self.env.context.get(
            "default_matchday_id"
        )
        court_id = values.get("court_id") or self.env.context.get("default_court_id")
        matchday = self.env["federation.matchday"].browse(matchday_id).exists()
        court = self.env["federation.playing.area"].browse(court_id).exists()
        if matchday:
            start, end = self._suggest_slot_window(matchday, court)
            values.setdefault("start_datetime", start)
            values.setdefault("end_datetime", end)
        return values

    @api.onchange("matchday_id", "court_id")
    def _onchange_slot_context(self):
        for rec in self:
            if not rec.matchday_id:
                continue
            start, end = rec._suggest_slot_window(rec.matchday_id, rec.court_id)
            rec.start_datetime = start
            rec.end_datetime = end

    @api.onchange("start_datetime")
    def _onchange_start_datetime(self):
        for rec in self:
            if not rec.start_datetime or not rec.matchday_id:
                continue
            duration = rec._suggest_duration_minutes(rec.matchday_id, rec.court_id)
            rec.end_datetime = rec.start_datetime + timedelta(minutes=duration)

    @api.model
    def _local_datetime_to_utc(self, local_value):
        """Convert a naive user-local datetime to the naive UTC value Odoo stores."""
        if not self.env.user.tz:
            return local_value
        import pytz

        timezone = pytz.timezone(self.env.user.tz)
        aware = timezone.localize(local_value, is_dst=None)
        return aware.astimezone(pytz.UTC).replace(tzinfo=None)

    @api.model
    def _first_start_for_matchday(self, matchday):
        hour = int(matchday.default_day_start_hour)
        minute = int(round((matchday.default_day_start_hour - hour) * 60))
        if minute == 60:
            hour += 1
            minute = 0
        local_start = datetime.combine(
            fields.Date.to_date(matchday.date), time(hour, minute)
        )
        return self._local_datetime_to_utc(local_start)

    @api.model
    def _suggest_duration_minutes(self, matchday, court=False):
        domain = [("matchday_id", "=", matchday.id)]
        if court:
            domain.append(("court_id", "=", court.id))
        previous = self.search(domain, order="end_datetime desc, id desc", limit=1)
        if previous and previous.start_datetime and previous.end_datetime:
            minutes = int(
                (previous.end_datetime - previous.start_datetime).total_seconds() // 60
            )
            if minutes > 0:
                return minutes
        return matchday.default_slot_duration_minutes or 40

    @api.model
    def _suggest_slot_window(self, matchday, court=False):
        """Start after the last slot on this court, otherwise on the match-day date."""
        domain = [("matchday_id", "=", matchday.id)]
        if court:
            domain.append(("court_id", "=", court.id))
        previous = self.search(domain, order="end_datetime desc, id desc", limit=1)
        start = (
            previous.end_datetime
            if previous
            else self._first_start_for_matchday(matchday)
        )
        duration = self._suggest_duration_minutes(matchday, court)
        return start, start + timedelta(minutes=duration)

    @api.constrains("start_datetime", "end_datetime")
    def _check_window(self):
        for r in self:
            if r.end_datetime <= r.start_datetime:
                raise ValidationError("A slot must end after it starts.")
