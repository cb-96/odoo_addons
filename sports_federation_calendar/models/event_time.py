from babel.dates import format_datetime
from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from ..time_policy import utc_to_local


class FederationEventTime(models.AbstractModel):
    _name = "federation.event.time"
    _description = "Consistent event-local time presentation"

    def _day(self, record, seen=None):
        if not record or not hasattr(record, "_fields"):
            return None
        record = record[:1]
        seen = set() if seen is None else seen
        key = (record._name, record.id)
        if key in seen:
            return None
        seen.add(key)
        if record._name == "federation.matchday":
            return record
        for field in (
            "matchday_id",
            "operational_slot_id",
            "published_slot_id",
            "match_id",
        ):
            if field in record._fields and record[field]:
                day = self._day(record[field], seen)
                if day:
                    return day
        return None

    @api.model
    def display(self, value, record=None):
        if not value:
            return ""
        timezone, reviewed = "UTC", True
        try:
            match = (
                record
                if record and record._name == "federation.match"
                else (
                    record.match_id if record and "match_id" in record._fields else None
                )
            )
            if match:
                timezone, reviewed = (
                    match.event_timezone_display,
                    match.event_timezone_display_reviewed,
                )
            else:
                day = self._day(record)
                if day:
                    timezone, reviewed = day.event_timezone, day.event_timezone_reviewed
        except AccessError:
            reviewed = False
        local = utc_to_local(value, timezone)
        locale = (self.env.lang or "en_US").replace("-", "_")
        text = format_datetime(local, format="medium", locale=locale)
        review = _(" · timezone needs review") if not reviewed else ""
        return "%s · %s%s" % (text, timezone, review)


class MatchEventTime(models.Model):
    _inherit = "federation.match"
    event_timezone_display = fields.Char(
        compute="_compute_event_timezone_display", compute_sudo=True
    )
    event_timezone_display_reviewed = fields.Boolean(
        compute="_compute_event_timezone_display", compute_sudo=True
    )

    @api.depends("date_scheduled")
    def _compute_event_timezone_display(self):
        # Only nonpersonal event metadata is projected onto an already-authorised match.
        service = self.env["federation.event.time"]
        for match in self:
            day = service._day(match)
            match.event_timezone_display = day.event_timezone if day else "UTC"
            match.event_timezone_display_reviewed = (
                day.event_timezone_reviewed if day else True
            )
