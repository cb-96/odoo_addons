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
    continue_court_timeline = fields.Boolean(
        string="Continue court timeline",
        default=True,
        help="When enabled, saved slots continue from the latest slot on the selected court and inherit its duration.",
    )

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

    @api.onchange("matchday_id")
    def _onchange_matchday_id(self):
        """Keep the initial proposal on the selected physical match-day date."""
        for rec in self:
            matchday = rec._persisted_matchday()
            if not matchday:
                continue
            start, end = rec._suggest_slot_window(matchday, False)
            rec.update({"start_datetime": start, "end_datetime": end})

    @api.onchange("court_id")
    def _onchange_court_id(self):
        """Rebase the row on the latest persisted slot for the selected court.

        Inline one2many rows can hold the parent as a virtual NewId. Searching
        with that virtual identifier returns no records, which previously made
        every court selection fall back to the match-day default. Resolve the
        persisted parent explicitly before querying prior slots.
        """
        for rec in self:
            # Keep the virtual parent so unsaved one2many siblings remain
            # available while the match-day form is still being edited.
            matchday = rec.matchday_id or rec._persisted_matchday()
            court = rec._persisted_court()
            if not matchday or not court:
                continue
            start, end = rec._suggest_slot_window_with_buffer(matchday, court)
            rec.update({"start_datetime": start, "end_datetime": end})

    def _persisted_matchday(self):
        self.ensure_one()
        matchday = self.matchday_id
        if matchday and matchday._origin and matchday._origin.id:
            return matchday._origin
        context_id = self.env.context.get("default_matchday_id")
        return self.env["federation.matchday"].browse(context_id).exists()

    def _persisted_court(self):
        self.ensure_one()
        court = self.court_id
        if court and court._origin and court._origin.id:
            return court._origin
        if court and court.id:
            return court
        return self.env["federation.playing.area"]

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

    def _latest_buffered_court_slot(self, court):
        """Return latest sibling row, including unsaved one2many commands."""
        self.ensure_one()
        if not self.matchday_id or not court:
            return self.env["federation.schedule.slot"]
        target_court = court._origin if court._origin and court._origin.id else court
        candidates = self.matchday_id.slot_ids.filtered(
            # Compare the raw identity tuple. Recordset equality is unreliable
            # for virtual NewId rows and previously either retained the current
            # row or discarded valid unsaved siblings.
            lambda slot: slot._ids != self._ids
            and slot.court_id
            and (
                slot.court_id._origin
                if slot.court_id._origin and slot.court_id._origin.id
                else slot.court_id
            )
            == target_court
            and slot.end_datetime
        )
        return candidates.sorted(
            lambda slot: (slot.end_datetime, slot.id or 0), reverse=True
        )[:1]

    def _suggest_slot_window_with_buffer(self, matchday, court):
        """Prefer the newest unsaved sibling before querying persisted slots."""
        self.ensure_one()
        previous = self._latest_buffered_court_slot(court)
        if previous:
            duration = int(
                (previous.end_datetime - previous.start_datetime).total_seconds() // 60
            )
            if duration <= 0:
                duration = matchday.default_slot_duration_minutes or 40
            return previous.end_datetime, previous.end_datetime + timedelta(
                minutes=duration
            )
        if not matchday.date and self.start_datetime and self.end_datetime:
            # A completely unsaved match-day has no physical date from which
            # to calculate a default. Keep the inline row's existing window.
            return self.start_datetime, self.end_datetime
        return self._suggest_slot_window(matchday, court)

    @api.model
    def _suggest_duration_minutes(self, matchday, court=False):
        matchday = matchday._origin if matchday and matchday._origin.id else matchday
        court = court._origin if court and court._origin.id else court
        if not court or not court.id:
            return matchday.default_slot_duration_minutes or 40
        previous = self._latest_court_slot(matchday, court)
        if previous and previous.start_datetime and previous.end_datetime:
            minutes = int(
                (previous.end_datetime - previous.start_datetime).total_seconds() // 60
            )
            if minutes > 0:
                return minutes
        return matchday.default_slot_duration_minutes or 40

    @api.model
    def _latest_court_slot(self, matchday, court):
        matchday = matchday._origin if matchday and matchday._origin.id else matchday
        court = court._origin if court and court._origin.id else court
        if not matchday or not matchday.id or not court or not court.id:
            return self.env["federation.schedule.slot"]
        return self.search(
            [("matchday_id", "=", matchday.id), ("court_id", "=", court.id)],
            order="end_datetime desc, id desc",
            limit=1,
        )

    @api.model
    def _suggest_slot_window(self, matchday, court=False):
        """Continue one court only; never borrow another court's timeline."""
        matchday = matchday._origin if matchday and matchday._origin.id else matchday
        court = court._origin if court and court._origin.id else court
        previous = (
            self._latest_court_slot(matchday, court) if court and court.id else False
        )
        start = (
            previous.end_datetime
            if previous
            else self._first_start_for_matchday(matchday)
        )
        duration = self._suggest_duration_minutes(matchday, court)
        return start, start + timedelta(minutes=duration)

    @api.model_create_multi
    def create(self, vals_list):
        """Normalize buffered inline rows as they are persisted.

        Odoo may keep several editable one2many rows client-side until the parent
        is saved. Their onchange calls cannot see those unsaved sibling rows.
        During create, rows are persisted sequentially, so each row can reliably
        continue from the row created immediately before it on the same court.
        """
        created = self.browse()
        for incoming in vals_list:
            vals = dict(incoming)
            if vals.get("continue_court_timeline", True):
                matchday = (
                    self.env["federation.matchday"]
                    .browse(vals.get("matchday_id"))
                    .exists()
                )
                court = (
                    self.env["federation.playing.area"]
                    .browse(vals.get("court_id"))
                    .exists()
                )
                if matchday and court:
                    previous = self._latest_court_slot(matchday, court)
                    provided_start = fields.Datetime.to_datetime(
                        vals.get("start_datetime")
                    )
                    provided_end = fields.Datetime.to_datetime(vals.get("end_datetime"))
                    provided_duration = (
                        int((provided_end - provided_start).total_seconds() // 60)
                        if provided_start
                        and provided_end
                        and provided_end > provided_start
                        else matchday.default_slot_duration_minutes or 40
                    )
                    if previous:
                        duration = (
                            int(
                                (
                                    previous.end_datetime - previous.start_datetime
                                ).total_seconds()
                                // 60
                            )
                            or matchday.default_slot_duration_minutes
                            or 40
                        )
                        start = previous.end_datetime
                    else:
                        # Keep a deliberately entered first-slot duration, but
                        # rebase stale defaults from another court to this day.
                        duration = provided_duration
                        start = self._first_start_for_matchday(matchday)
                    vals["start_datetime"] = start
                    vals["end_datetime"] = start + timedelta(minutes=duration)
            created |= super(FederationScheduleSlot, self).create([vals])
        return created

    @api.constrains("start_datetime", "end_datetime")
    def _check_window(self):
        for r in self:
            if r.end_datetime <= r.start_datetime:
                raise ValidationError("A slot must end after it starts.")
