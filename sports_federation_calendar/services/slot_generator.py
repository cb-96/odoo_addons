from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationSlotGenerator(models.AbstractModel):
    _name = "federation.slot.generator"
    _description = "Match-Day Slot Generator"

    @api.model
    def _local_datetime(self, matchday, hour_value):
        hour = int(hour_value)
        minute = round((hour_value - hour) * 60)
        if minute == 60:
            hour += 1
            minute = 0
        day = fields.Date.to_date(matchday.date)
        if hour == 24:
            local_value = datetime.combine(day + timedelta(days=1), time.min)
        else:
            local_value = datetime.combine(day, time(hour=hour, minute=minute))
        timezone = pytz.timezone(self.env.user.tz or "UTC")
        return timezone.localize(local_value).astimezone(pytz.UTC).replace(tzinfo=None)

    @staticmethod
    def _overlaps(start_a, end_a, start_b, end_b):
        return start_a < end_b and start_b < end_a

    @api.model
    def _blackout_constraints(self, matchday, court, start, end):
        return matchday.venue_id.blackout_window_ids.filtered(
            lambda constraint: constraint.active
            and (not constraint.playing_area_id or constraint.playing_area_id == court)
            and self._overlaps(
                start,
                end,
                fields.Datetime.to_datetime(constraint.date_start),
                fields.Datetime.to_datetime(constraint.date_end),
            )
        )

    @api.model
    def plan(
        self,
        matchday,
        courts,
        start_hour,
        end_hour,
        duration_minutes,
        noon_pause=False,
        noon_pause_minutes=60,
    ):
        matchday.ensure_one()
        if matchday.state not in ("draft", "capacity_ready"):
            raise ValidationError(
                _("Slots can only be regenerated before scheduling starts.")
            )
        if not courts:
            raise ValidationError(_("Select at least one playing area."))
        if courts.filtered(lambda court: court.venue_id != matchday.venue_id):
            raise ValidationError(
                _("Every selected playing area must belong to the match-day venue.")
            )
        if end_hour <= start_hour or duration_minutes <= 0:
            raise ValidationError(_("Provide a valid positive slot window."))
        if noon_pause and noon_pause_minutes <= 0:
            raise ValidationError(_("Noon pause duration must be positive."))

        start = self._local_datetime(matchday, start_hour)
        end = self._local_datetime(matchday, end_hour)
        pause_start = self._local_datetime(matchday, 12.0) if noon_pause else False
        pause_end = (
            pause_start + timedelta(minutes=noon_pause_minutes)
            if pause_start
            else False
        )
        available = []
        breaks = []
        blocked = 0
        duration = timedelta(minutes=duration_minutes)

        for court in courts.sorted(lambda item: item.id):
            if pause_start and start < pause_end and pause_start < end:
                breaks.append(
                    {
                        "matchday_id": matchday.id,
                        "court_id": court.id,
                        "start_datetime": max(start, pause_start),
                        "end_datetime": min(end, pause_end),
                        "state": "break",
                        "note": _("Noon pause"),
                    }
                )
            pointer = start
            while pointer + duration <= end:
                candidate_end = pointer + duration
                if pause_start and pointer < pause_end and pause_start < candidate_end:
                    pointer = pause_end
                    continue
                constraints = self._blackout_constraints(
                    matchday, court, pointer, candidate_end
                )
                if constraints:
                    blocked += 1
                    pointer = max(
                        candidate_end,
                        max(
                            fields.Datetime.to_datetime(item.date_end)
                            for item in constraints
                        ),
                    )
                    continue
                available.append(
                    {
                        "matchday_id": matchday.id,
                        "court_id": court.id,
                        "start_datetime": pointer,
                        "end_datetime": candidate_end,
                        "state": "available",
                    }
                )
                pointer = candidate_end
        return {
            "available": available,
            "breaks": breaks,
            "blocked_count": blocked,
        }

    @api.model
    def generate_plan(
        self,
        matchday,
        courts,
        start_hour,
        end_hour,
        duration_minutes,
        noon_pause=False,
        noon_pause_minutes=60,
        replace_existing=False,
    ):
        matchday.ensure_one()
        if matchday.slot_ids and not replace_existing:
            raise ValidationError(
                _("Existing slots must be explicitly replaced before generation.")
            )
        plan = self.plan(
            matchday,
            courts,
            start_hour,
            end_hour,
            duration_minutes,
            noon_pause=noon_pause,
            noon_pause_minutes=noon_pause_minutes,
        )
        if not plan["available"]:
            raise ValidationError(
                _("The selected window produces no playable fixture slots.")
            )
        if replace_existing:
            matchday.slot_ids.unlink()
        matchday.write(
            {
                "default_day_start_hour": start_hour,
                "default_slot_duration_minutes": duration_minutes,
            }
        )
        generated_values = [
            dict(values, continue_court_timeline=False)
            for values in plan["available"] + plan["breaks"]
        ]
        return self.env["federation.schedule.slot"].create(generated_values)

    @api.model
    def generate(
        self,
        matchday,
        courts,
        start_time,
        end_time,
        duration_minutes,
        buffer_minutes=0,
    ):
        """Compatibility entry point for callers using HH:MM strings."""
        start = datetime.strptime(start_time, "%H:%M").time()
        end = datetime.strptime(end_time, "%H:%M").time()
        start_hour = start.hour + start.minute / 60
        end_hour = end.hour + end.minute / 60
        return self.generate_plan(
            matchday,
            courts,
            start_hour,
            end_hour,
            duration_minutes + max(buffer_minutes, 0),
            replace_existing=True,
        )
