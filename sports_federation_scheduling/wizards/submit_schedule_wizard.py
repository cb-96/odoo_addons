from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationScheduleSubmitWizard(models.TransientModel):
    _name = "federation.schedule.submit.wizard"
    _description = "Submit Schedule for Independent Review"

    schedule_id = fields.Many2one(
        "federation.schedule", required=True, readonly=True, ondelete="cascade"
    )
    expected_revision = fields.Integer(required=True, readonly=True)
    warning_count = fields.Integer(readonly=True)
    warning_summary = fields.Text(readonly=True)
    warning_override_reason = fields.Text(
        string="Warning override reason",
        help="Required when the submitted schedule still contains non-blocking warnings.",
    )

    def action_submit(self):
        self.ensure_one()
        if self.schedule_id.revision != self.expected_revision:
            raise ValidationError(
                _("The schedule changed after this confirmation was opened. Refresh and retry.")
            )
        if self.warning_count and not (self.warning_override_reason or "").strip():
            raise ValidationError(_("Explain why the remaining warnings are acceptable."))
        return self.schedule_id.action_submit_for_review(
            warning_override_reason=self.warning_override_reason
        )
