from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationCompetitionGamedaySetupWizardEnhancements(models.TransientModel):
    _inherit = "federation.competition.gameday.setup.wizard"

    repeat_every_weeks = fields.Integer(default=1, string="Every (weeks)")
    repeat_count = fields.Integer(default=1, string="Number of game days")
    skip_dates = fields.Char(
        string="Skip dates",
        help="Dates without games, separated by commas (for example holidays). "
        "Skipped dates do not count towards the number of game days.",
    )

    @api.model
    def _gameday_name(self, date, divisions):
        name = _("Game Day %(date)s", date=fields.Date.to_string(date))
        if divisions:
            name = "%s (%s)" % (name, ", ".join(divisions.mapped("name")))
        return name

    def _parsed_skip_dates(self):
        self.ensure_one()
        dates = set()
        for raw in (self.skip_dates or "").replace(";", ",").split(","):
            raw = raw.strip()
            if not raw:
                continue
            parsed = None
            for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
                try:
                    parsed = datetime.strptime(raw, pattern).date()
                    break
                except ValueError:
                    continue
            if not parsed:
                raise ValidationError(
                    _("Could not read the skip date '%(value)s'. Use dd/mm/yyyy.", value=raw)
                )
            dates.add(parsed)
        return dates

    def action_add_recurring_days(self):
        self.ensure_one()
        if not self.default_venue_id:
            raise ValidationError(_("Select a venue before adding game days."))
        if self.repeat_every_weeks < 1 or self.repeat_count < 1:
            raise ValidationError(_("Repeat values must be positive."))
        date = self.new_date or self.edition_id.date_start or fields.Date.context_today(self)
        commands = []
        courts = self.default_venue_id.playing_area_ids.filtered("active")
        skipped = self._parsed_skip_dates()
        # Two game days may share a date (for example at different venues);
        # only an identical date and venue counts as a duplicate.
        existing = {(line.date, line.venue_id.id) for line in self.line_ids}
        day_date = date
        added = 0
        guard = 0
        while added < self.repeat_count and guard < 520:
            guard += 1
            current = day_date
            day_date = day_date + timedelta(weeks=self.repeat_every_weeks)
            if current in skipped or (current, self.default_venue_id.id) in existing:
                continue
            added += 1
            day_date_value = current
            commands.append(
                fields.Command.create(
                    {
                        "name": self._gameday_name(day_date_value, self.default_division_ids),
                        "division_ids": [fields.Command.set(self.default_division_ids.ids)],
                        "date": day_date_value,
                        "venue_id": self.default_venue_id.id,
                        "start_hour": self.default_start_hour,
                        "end_hour": self.default_end_hour,
                        "slot_duration_minutes": self.default_slot_duration_minutes,
                        "court_ids": [fields.Command.set(courts.ids)],
                    }
                )
            )
        self.line_ids = commands
        self.new_date = day_date
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
                    "name": self._gameday_name(day_date, source.division_ids),
                    "division_ids": [fields.Command.set(source.division_ids.ids)],
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
