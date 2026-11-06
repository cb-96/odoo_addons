import pytz
from odoo import fields, models


class EventTimezoneReview(models.TransientModel):
    _name = "federation.event.timezone.review"
    _description = "Review historical event timezone"
    matchday_id = fields.Many2one("federation.matchday", required=True, readonly=True)
    timezone = fields.Selection(
        [(zone, zone) for zone in pytz.all_timezones], required=True
    )
    reason = fields.Text(required=True, string="Timezone evidence")

    def action_confirm(self):
        self.ensure_one()
        self.matchday_id._review_event_timezone(self.timezone, self.reason)
        return {"type": "ir.actions.act_window_close"}
