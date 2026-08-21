from datetime import datetime, timedelta
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationSlotGenerator(models.AbstractModel):
    _name = "federation.slot.generator"
    _description = "Match-Day Slot Generator"

    @api.model
    def generate(
        self, matchday, courts, start_time, end_time, duration_minutes, buffer_minutes=0
    ):
        matchday.ensure_one()
        if matchday.state not in ("draft", "capacity_ready"):
            raise ValidationError(
                _("Slots can only be regenerated before scheduling starts.")
            )
        start = datetime.combine(
            fields.Date.to_date(matchday.date),
            datetime.strptime(start_time, "%H:%M").time(),
        )
        end = datetime.combine(
            fields.Date.to_date(matchday.date),
            datetime.strptime(end_time, "%H:%M").time(),
        )
        if end <= start or duration_minutes <= 0:
            raise ValidationError(_("Provide a valid positive slot window."))
        matchday.slot_ids.unlink()
        vals = []
        for court in courts:
            pointer = start
            while pointer + timedelta(minutes=duration_minutes) <= end:
                vals.append(
                    {
                        "matchday_id": matchday.id,
                        "court_id": court.id,
                        "start_datetime": pointer,
                        "end_datetime": pointer + timedelta(minutes=duration_minutes),
                    }
                )
                pointer += timedelta(minutes=duration_minutes + max(buffer_minutes, 0))
        return self.env["federation.schedule.slot"].create(vals)
