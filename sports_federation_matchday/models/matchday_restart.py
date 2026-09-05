from odoo import _, models
from odoo.exceptions import ValidationError


class FederationMatchdayRestart(models.Model):
    _inherit = "federation.matchday"

    def _assert_restartable_from_scratch(self):
        self.ensure_one()
        if self.state in ("open", "closed"):
            raise ValidationError(
                _("Open or closed match days cannot be restarted from scratch.")
            )
        publications = (
            self.env["federation.schedule.publication"]
            .sudo()
            .search_count([("matchday_id", "=", self.id)])
        )
        if publications or self.current_publication_id:
            raise ValidationError(
                _(
                    "This match day has publication history. Create a governed "
                    "schedule revision instead of deleting audit evidence."
                )
            )
        schedules = (
            self.env["federation.schedule"]
            .sudo()
            .with_context(active_test=False)
            .search([("matchday_id", "=", self.id)])
        )
        reviews = (
            self.env["federation.schedule.review"]
            .sudo()
            .search_count([("schedule_id", "in", schedules.ids)])
        )
        if reviews:
            raise ValidationError(
                _(
                    "This match day has schedule-review history. Withdraw or "
                    "revise the schedule; submitted review evidence cannot be deleted."
                )
            )
        immutable = schedules.filtered(
            lambda schedule: schedule.state not in ("draft", "changes_requested")
        )
        if immutable:
            raise ValidationError(
                _(
                    "Only draft or change-requested schedules can be discarded. "
                    "Return the schedule to an editable state first."
                )
            )
        return True

    def _delete_restartable_schedules(self):
        """Remove every mutable schedule, including records hidden by rules."""
        self.ensure_one()
        self._assert_restartable_from_scratch()
        schedules = (
            self.env["federation.schedule"]
            .sudo()
            .with_context(active_test=False)
            .search([("matchday_id", "=", self.id)])
        )
        schedules.unlink()

    def unlink(self):
        """Delete draft match days together with their mutable schedules.

        ``federation.schedule.matchday_id`` deliberately uses a restrictive
        foreign key so published schedule history cannot be orphaned. Draft
        schedules are disposable planning data, however, and should not make
        an otherwise deletable draft match day impossible to remove.
        """
        for matchday in self:
            matchday._delete_restartable_schedules()
        return super().unlink()

    def action_open_restart_from_scratch(self):
        self.ensure_one()
        self.env["federation.competition.role.assignment"].assert_role(
            self.edition_id, "matchday_manager", "competition_director"
        )
        self._assert_restartable_from_scratch()
        wizard = self.env["federation.matchday.restart.wizard"].create(
            {"matchday_id": self.id}
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Restart Match Day from Scratch"),
            "res_model": "federation.matchday.restart.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }
