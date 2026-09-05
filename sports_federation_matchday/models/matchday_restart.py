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
        publications = self.env["federation.schedule.publication"].search_count(
            [("matchday_id", "=", self.id)]
        )
        if publications or self.current_publication_id:
            raise ValidationError(
                _(
                    "This match day has publication history. Create a governed "
                    "schedule revision instead of deleting audit evidence."
                )
            )
        schedules = self.env["federation.schedule"].search(
            [("matchday_id", "=", self.id)]
        )
        reviews = self.env["federation.schedule.review"].search_count(
            [("schedule_id", "in", schedules.ids)]
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
