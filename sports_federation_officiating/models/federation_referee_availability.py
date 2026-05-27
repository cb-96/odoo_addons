from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationRefereeAvailability(models.Model):
    _name = "federation.referee.availability"
    _description = "Referee Availability Window"
    _order = "date_start, id"

    name = fields.Char(string="Label", compute="_compute_name", store=True)
    referee_id = fields.Many2one(
        "federation.referee",
        string="Referee",
        required=True,
        ondelete="cascade",
        index=True,
    )
    date_start = fields.Datetime(string="Start", required=True)
    date_end = fields.Datetime(string="End", required=True)
    note = fields.Text(string="Notes")
    active = fields.Boolean(default=True)

    @api.depends("referee_id", "date_start", "date_end")
    def _compute_name(self):
        for record in self:
            start_label = (
                fields.Datetime.to_datetime(record.date_start).strftime("%Y-%m-%d %H:%M")
                if record.date_start
                else _("Start")
            )
            end_label = (
                fields.Datetime.to_datetime(record.date_end).strftime("%Y-%m-%d %H:%M")
                if record.date_end
                else _("End")
            )
            referee_label = record.referee_id.display_name or _("Referee")
            record.name = _(
                "%(referee)s %(start)s-%(end)s",
                referee=referee_label,
                start=start_label,
                end=end_label,
            )

    @api.constrains("date_start", "date_end")
    def _check_window(self):
        for record in self:
            if record.date_end <= record.date_start:
                raise ValidationError(
                    _("Referee availability must end after it starts.")
                )