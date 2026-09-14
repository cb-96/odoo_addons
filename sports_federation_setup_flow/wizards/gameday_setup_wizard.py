from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationCompetitionGamedaySetupWizard(models.TransientModel):
    _name = "federation.competition.gameday.setup.wizard"
    _description = "Define Competition Game Days"

    edition_id = fields.Many2one("federation.competition.edition", required=True, readonly=True)
    line_ids = fields.One2many("federation.competition.gameday.setup.line", "wizard_id")
    new_date = fields.Date(default=fields.Date.context_today)
    default_venue_id = fields.Many2one("federation.venue")
    default_start_hour = fields.Float(default=9.0)
    default_end_hour = fields.Float(default=18.0)
    default_slot_duration_minutes = fields.Integer(default=40)

    @api.model_create_multi
    def create(self, values_list):
        records = super().create(values_list)
        records._load_existing_days()
        return records

    def _load_existing_days(self):
        for wizard in self.filtered(lambda item: not item.line_ids):
            days = self.env["federation.matchday"].search(
                [("edition_id", "=", wizard.edition_id.id)], order="date,id"
            )
            wizard.line_ids = [
                fields.Command.create(
                    {
                        "matchday_id": day.id,
                        "name": day.name,
                        "date": day.date,
                        "venue_id": day.venue_id.id,
                        "start_hour": day.default_day_start_hour,
                        "end_hour": day.default_day_end_hour,
                        "slot_duration_minutes": day.default_slot_duration_minutes,
                        "court_ids": [fields.Command.set(day.planning_court_ids.ids)],
                        "noon_pause": day.default_noon_pause,
                        "noon_pause_minutes": day.default_noon_pause_minutes,
                    }
                )
                for day in days
            ]

    def action_add_day(self):
        self.ensure_one()
        date = self.new_date
        if not date:
            date = self.edition_id.date_start or fields.Date.context_today(self)
        self.line_ids = [
            fields.Command.create(
                {
                    "name": _("Game Day %(date)s", date=fields.Date.to_string(date)),
                    "date": date,
                    "venue_id": self.default_venue_id.id,
                    "start_hour": self.default_start_hour,
                    "end_hour": self.default_end_hour,
                    "slot_duration_minutes": self.default_slot_duration_minutes,
                }
            )
        ]
        self.new_date = date + timedelta(days=7)
        return self._reopen()

    def action_save_close(self):
        self._save_days()
        return self.edition_id.get_formview_action()

    def action_save_continue(self):
        self._save_days()
        return self.edition_id.action_continue_setup()

    def _save_days(self):
        self.ensure_one()
        if not self.line_ids:
            raise ValidationError(_("Add at least one game day."))
        for line in self.line_ids:
            line._validate_line()
            values = line._matchday_values(self.edition_id)
            if line.matchday_id:
                line.matchday_id.write(values)
            else:
                line.matchday_id = self.env["federation.matchday"].create(values)
        return True

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }


class FederationCompetitionGamedaySetupLine(models.TransientModel):
    _name = "federation.competition.gameday.setup.line"
    _description = "Competition Game Day Setup Line"
    _order = "date,id"

    wizard_id = fields.Many2one("federation.competition.gameday.setup.wizard", required=True, ondelete="cascade")
    matchday_id = fields.Many2one("federation.matchday", readonly=True)
    name = fields.Char(required=True)
    date = fields.Date(required=True)
    venue_id = fields.Many2one("federation.venue", required=True)
    court_ids = fields.Many2many("federation.playing.area", string="Courts")
    start_hour = fields.Float(required=True, default=9.0)
    end_hour = fields.Float(required=True, default=18.0)
    slot_duration_minutes = fields.Integer(required=True, default=40)
    noon_pause = fields.Boolean()
    noon_pause_minutes = fields.Integer(default=60)
    estimated_capacity = fields.Integer(compute="_compute_estimated_capacity")

    @api.depends("court_ids", "start_hour", "end_hour", "slot_duration_minutes", "noon_pause", "noon_pause_minutes")
    def _compute_estimated_capacity(self):
        for line in self:
            minutes = max(0, int((line.end_hour - line.start_hour) * 60))
            if line.noon_pause:
                minutes = max(0, minutes - line.noon_pause_minutes)
            line.estimated_capacity = (
                len(line.court_ids) * (minutes // line.slot_duration_minutes)
                if line.slot_duration_minutes > 0
                else 0
            )

    @api.onchange("venue_id")
    def _onchange_venue_id(self):
        self.court_ids = self.venue_id.playing_area_ids.filtered("active")

    def _validate_line(self):
        self.ensure_one()
        if self.end_hour <= self.start_hour:
            raise ValidationError(_("Game-day end must be after its start."))
        if self.slot_duration_minutes <= 0:
            raise ValidationError(_("Slot duration must be positive."))
        if not self.court_ids:
            raise ValidationError(_("Select at least one court for %s.") % self.name)

    def _matchday_values(self, edition):
        return {
            "name": self.name,
            "edition_id": edition.id,
            "date": self.date,
            "venue_id": self.venue_id.id,
            "default_day_start_hour": self.start_hour,
            "default_day_end_hour": self.end_hour,
            "default_slot_duration_minutes": self.slot_duration_minutes,
            "planning_court_ids": [fields.Command.set(self.court_ids.ids)],
            "default_noon_pause": self.noon_pause,
            "default_noon_pause_minutes": self.noon_pause_minutes,
        }
