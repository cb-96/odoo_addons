"""Replay-safe publication on top of the approval commands.

This extends ``federation.schedule.approval.commands``, so it lives with the
services that define that model and is imported after them. Odoo builds models
in import order; an extension imported before its base model stops the
registry from loading.
"""

from odoo import _, api, models
from odoo.exceptions import ValidationError

from ..planning_tokens import with_published_planning_token


class PublicationReplay(models.AbstractModel):
    _inherit = "federation.schedule.approval.commands"

    def _link_match_to_publication(self, match, assignment, publication):
        if match.state not in ("draft", "scheduled"):
            if match.published_slot_id != assignment.slot_id:
                raise ValidationError(
                    _("A publication cannot move a started or completed match.")
                )
            # Keep the operational record's original publication provenance.
            return True
        return super()._link_match_to_publication(
            with_published_planning_token(match),
            assignment,
            publication,
        )

    @api.model
    def publish(self, schedule_id, reason=False, expected_publication_id=None):
        schedule = self.env["federation.schedule"].browse(int(schedule_id)).exists()
        if not schedule:
            raise ValidationError(_("The schedule no longer exists."))
        self.env["federation.competition.role.assignment"].assert_role(
            schedule.edition_id,
            "schedule_planner",
            "schedule_approver",
            "competition_director",
        )
        # The role check above authorizes the publication. Planners do not
        # need Calendar Planner rights to see the game day being published, so
        # read it elevated, like the base publish command does.
        matchday = schedule.sudo().matchday_id
        self.env.cr.execute(
            "SELECT id FROM federation_matchday WHERE id = %s FOR UPDATE",
            [matchday.id],
        )
        schedule.invalidate_recordset()
        matchday.invalidate_recordset()
        live = matchday.current_publication_id
        if (
            live
            and live.state == "live"
            and live.schedule_id == schedule
            and schedule.state == "published"
        ):
            if (
                expected_publication_id is not None
                and expected_publication_id != live.id
            ):
                raise ValidationError(
                    _("Publication changed. Refresh before replaying the command.")
                )
            return live
        with self.env.cr.savepoint():
            return super().publish(
                schedule_id,
                reason=reason,
                expected_publication_id=expected_publication_id,
            )
