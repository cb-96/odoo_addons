"""Confirm publication when some game days have short rest between matches."""

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationSchedulePublishConfirmWizard(models.TransientModel):
    _name = "federation.schedule.publish.confirm.wizard"
    _description = "Confirm Schedule Publication"

    edition_id = fields.Many2one(
        "federation.competition.edition", required=True, readonly=True
    )
    details_html = fields.Html(readonly=True, sanitize=True)
    warning_day_count = fields.Integer(readonly=True)
    reason = fields.Char(
        string="Reason",
        help="Stored with each accepted schedule in its change history.",
    )

    def action_publish_all(self):
        """Publish every game day and record the reason for accepting short rest."""
        self.ensure_one()
        reason = (self.reason or "").strip()
        if not reason:
            raise ValidationError(_("Enter a reason for accepting the short rest."))
        return self.edition_id.action_publish_competition_schedule(
            warning_override_reason=reason
        )

    def action_publish_others(self):
        """Publish only the game days without short rest."""
        self.ensure_one()
        return self.edition_id.with_context(
            skip_warning_days=True
        ).action_publish_competition_schedule()

    def action_regenerate(self):
        """Go back to schedule generation to change rest, courts or game days."""
        self.ensure_one()
        return self.edition_id.action_setup_schedule()
