from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationSchedulePublishWizard(models.TransientModel):
    _name = "federation.schedule.publish.wizard"
    _description = "Publish Approved Schedule"

    review_id = fields.Many2one(
        "federation.schedule.review", required=True, readonly=True, ondelete="cascade"
    )
    schedule_id = fields.Many2one(related="review_id.schedule_id", readonly=True)
    matchday_id = fields.Many2one(related="schedule_id.matchday_id", readonly=True)
    current_publication_id = fields.Many2one(
        "federation.schedule.publication", readonly=True
    )
    replacement_required = fields.Boolean(readonly=True)
    expected_publication_id = fields.Integer(required=True, readonly=True)
    reason = fields.Text(
        string="Publication reason",
        help="Required when replacing the current live publication.",
    )

    def action_publish(self):
        self.ensure_one()
        current = self.matchday_id.sudo().current_publication_id
        current_id = current.id if current and current.state == "live" else 0
        if current_id != self.expected_publication_id:
            raise ValidationError(
                _(
                    "The live publication changed after this dialog opened. Refresh and retry."
                )
            )
        if self.replacement_required and not (self.reason or "").strip():
            raise ValidationError(
                _("Explain why the live publication is being replaced.")
            )
        publication = self.env["federation.schedule.approval.commands"].publish(
            self.schedule_id.id,
            reason=self.reason,
            expected_publication_id=self.expected_publication_id,
        )
        return publication.action_open_publication()
