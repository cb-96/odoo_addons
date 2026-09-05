from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationMatchdayRestartWizard(models.TransientModel):
    _name = "federation.matchday.restart.wizard"
    _description = "Restart Match Day Planning from Scratch"

    matchday_id = fields.Many2one(
        "federation.matchday", required=True, readonly=True, ondelete="cascade"
    )
    reason = fields.Text(required=True)
    confirmation = fields.Boolean(
        string=(
            "I understand that the current unpublished planning data will be deleted"
        ),
        required=True,
    )

    def action_restart(self):
        self.ensure_one()
        if not self.confirmation:
            raise ValidationError(
                _("Confirm the destructive restart before continuing.")
            )
        matchday = self.matchday_id.exists()
        if not matchday:
            raise ValidationError(_("The match day no longer exists."))
        matchday._assert_restartable_from_scratch()

        replacement = self.env["federation.matchday"].create(
            {
                "name": matchday.name,
                "edition_id": matchday.edition_id.id,
                "date": matchday.date,
                "venue_id": matchday.venue_id.id,
                "default_day_start_hour": matchday.default_day_start_hour,
                "default_slot_duration_minutes": matchday.default_slot_duration_minutes,
            }
        )
        schedules = self.env["federation.schedule"].search(
            [("matchday_id", "=", matchday.id)]
        )
        schedules.unlink()
        matchday.unlink()
        replacement.message_post(
            body=_(
                "Planning restarted from scratch. Reason: %(reason)s",
                reason=self.reason,
            )
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Match Day"),
            "res_model": "federation.matchday",
            "res_id": replacement.id,
            "view_mode": "form",
            "target": "current",
        }
