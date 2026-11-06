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
    matchday_state = fields.Selection(
        related="schedule_id.matchday_id.state", readonly=True
    )
    published_assignment_count = fields.Integer(
        compute="_compute_recovery_summary",
        string="Published Assignments",
        readonly=True,
    )
    recovery_summary = fields.Text(compute="_compute_recovery_summary", readonly=True)

    def _compute_recovery_summary(self):
        for wizard in self:
            schedule = wizard.schedule_id
            wizard.published_assignment_count = len(schedule.assignment_ids)
            wizard.recovery_summary = _(
                "Current publication: %(schedule)s, revision %(revision)s, "
                "%(assignments)s assignments. The published snapshot remains "
                "immutable. Create the amendment, update the replacement, submit it "
                "for independent review, then publish it to supersede the current "
                "version.",
                schedule=schedule.display_name or _("No schedule selected"),
                revision=schedule.revision or 0,
                assignments=len(schedule.assignment_ids),
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
