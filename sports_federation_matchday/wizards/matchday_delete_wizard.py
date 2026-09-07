from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.sports_federation_base.destructive_tokens import (
    MATCHDAY_DESTRUCTIVE_DELETE_CONTEXT_KEY,
    MATCHDAY_DESTRUCTIVE_DELETE_TOKEN,
)


class FederationMatchdayDeleteWizard(models.TransientModel):
    _name = "federation.matchday.delete.wizard"
    _description = "Delete Closed Match Day"

    matchday_id = fields.Many2one(
        "federation.matchday", required=True, readonly=True, ondelete="cascade"
    )
    impact_summary = fields.Text(compute="_compute_impact_summary")
    reason = fields.Text(string="Reason")

    @api.depends("matchday_id")
    def _compute_impact_summary(self):
        for wizard in self:
            if not wizard.matchday_id:
                wizard.impact_summary = False
                continue
            impact = wizard.matchday_id._closed_delete_impact()
            wizard.impact_summary = _(
                "This will permanently delete the match day and its working "
                "schedule data: %(schedules)s schedule(s), %(publications)s "
                "publication(s), %(sessions)s execution session(s), and "
                "%(deviations)s operational deviation(s). %(matches)s match(es) "
                "will be detached from the deleted publication and calendar "
                "slots, but the match records will remain in the competition.",
                schedules=impact["schedule_count"],
                publications=impact["publication_count"],
                sessions=impact["session_count"],
                deviations=impact["deviation_count"],
                matches=impact["match_count"],
            )

    def action_delete(self):
        self.ensure_one()
        reason = (self.reason or "").strip()
        if not reason:
            raise ValidationError(
                _("Enter a reason before permanently deleting the match day.")
            )
        matchday = self.matchday_id.exists()
        if not matchday:
            raise ValidationError(_("The match day no longer exists."))
        if matchday.state != "closed":
            raise ValidationError(
                _("This action is only available for closed match days.")
            )
        self.env["federation.competition.role.assignment"].assert_role(
            matchday.edition_id, "matchday_manager", "competition_director"
        )
        matchday.with_context(
            **{
                MATCHDAY_DESTRUCTIVE_DELETE_CONTEXT_KEY:
                    MATCHDAY_DESTRUCTIVE_DELETE_TOKEN
            },
            matchday_delete_reason=reason,
        ).unlink()
        return {
            "type": "ir.actions.act_window_close",
        }
