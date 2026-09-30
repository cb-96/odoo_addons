from datetime import timedelta

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationCompetitionGamedaySetupWizardEnhancements(models.TransientModel):
    _inherit = "federation.competition.gameday.setup.wizard"

    repeat_every_weeks = fields.Integer(default=1, string="Repeat every")
    repeat_count = fields.Integer(default=1, string="Number of game days")

    def action_add_recurring_days(self):
        self.ensure_one()
        if not self.default_venue_id:
            raise ValidationError(_("Select a venue before adding game days."))
        if self.repeat_every_weeks < 1 or self.repeat_count < 1:
            raise ValidationError(_("Repeat values must be positive."))
        date = self.new_date or self.edition_id.date_start or fields.Date.context_today(self)
        commands = []
        courts = self.default_venue_id.playing_area_ids.filtered("active")
        for index in range(self.repeat_count):
            day_date = date + timedelta(weeks=index * self.repeat_every_weeks)
            commands.append(
                fields.Command.create(
                    {
                        "name": _("Game Day %(date)s", date=fields.Date.to_string(day_date)),
                        "date": day_date,
                        "venue_id": self.default_venue_id.id,
                        "start_hour": self.default_start_hour,
                        "end_hour": self.default_end_hour,
                        "slot_duration_minutes": self.default_slot_duration_minutes,
                        "court_ids": [fields.Command.set(courts.ids)],
                    }
                )
            )
        self.line_ids = commands
        self.new_date = date + timedelta(weeks=self.repeat_count * self.repeat_every_weeks)
        return self._reopen()

    def action_copy_last_day(self):
        self.ensure_one()
        last = self.line_ids.sorted(lambda line: (line.date, line.id))[-1:]
        if not last:
            raise ValidationError(_("Add a game day before copying it."))
        source = last[0]
        day_date = source.date + timedelta(weeks=max(1, self.repeat_every_weeks))
        self.line_ids = [
            fields.Command.create(
                {
                    "name": _("Game Day %(date)s", date=fields.Date.to_string(day_date)),
                    "date": day_date,
                    "venue_id": source.venue_id.id,
                    "start_hour": source.start_hour,
                    "end_hour": source.end_hour,
                    "slot_duration_minutes": source.slot_duration_minutes,
                    "court_ids": [fields.Command.set(source.court_ids.ids)],
                    "noon_pause": source.noon_pause,
                    "noon_pause_minutes": source.noon_pause_minutes,
                }
            )
        ]
        self.new_date = day_date + timedelta(weeks=max(1, self.repeat_every_weeks))
        return self._reopen()
