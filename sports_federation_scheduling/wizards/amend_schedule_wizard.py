from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationScheduleAmendWizard(models.TransientModel):
    _name = "federation.schedule.amend.wizard"
    _description = "Amend Published Schedule"

    schedule_id = fields.Many2one(
        "federation.schedule", required=True, readonly=True, ondelete="cascade"
    )
    reason = fields.Text(
        required=True,
        help="Explain why a replacement schedule revision is required.",
    )

    def action_amend(self):
        self.ensure_one()
        if not (self.reason or "").strip():
            raise ValidationError(_("Enter a reason for amending the schedule."))
        replacement = self.schedule_id.action_create_revision(self.reason.strip())
        return {
            "type": "ir.actions.act_window",
            "name": _("Schedule Amendment"),
            "res_model": "federation.schedule",
            "res_id": replacement.id,
            "view_mode": "form",
            "target": "current",
        }
