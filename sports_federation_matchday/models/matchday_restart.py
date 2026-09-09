from odoo import _, models
from odoo.exceptions import ValidationError

from odoo.addons.sports_federation_base.destructive_tokens import (
    MATCHDAY_DESTRUCTIVE_DELETE_CONTEXT_KEY,
    MATCHDAY_DESTRUCTIVE_DELETE_TOKEN,
)


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

    def _closed_delete_impact(self):
        self.ensure_one()
        Schedule = (
            self.env["federation.schedule"].sudo().with_context(active_test=False)
        )
        schedules = Schedule.search([("matchday_id", "=", self.id)])
        publications = (
            self.env["federation.schedule.publication"]
            .sudo()
            .search([("schedule_id", "in", schedules.ids)])
        )
        sessions = (
            self.env["federation.matchday.session"]
            .sudo()
            .search([("matchday_id", "=", self.id)])
        )
        deviations = (
            self.env["federation.matchday.deviation"]
            .sudo()
            .search([("matchday_id", "=", self.id)])
        )
        slots = (
            self.env["federation.schedule.slot"]
            .sudo()
            .search([("matchday_id", "=", self.id)])
        )
        matches = (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    "|",
                    "|",
                    ("schedule_publication_id", "in", publications.ids),
                    ("published_slot_id", "in", slots.ids),
                    ("operational_slot_id", "in", slots.ids),
                ]
            )
        )
        return {
            "schedule_count": len(schedules),
            "publication_count": len(publications),
            "session_count": len(sessions),
            "deviation_count": len(deviations),
            "match_count": len(matches),
        }

    def _delete_closed_matchday_data(self):
        """Remove closed-day data only after explicit destructive confirmation."""
        self.ensure_one()
        if self.state != "closed":
            raise ValidationError(_("Only closed match days can use this action."))
        if (
            self.env.context.get(MATCHDAY_DESTRUCTIVE_DELETE_CONTEXT_KEY)
            is not MATCHDAY_DESTRUCTIVE_DELETE_TOKEN
        ):
            raise ValidationError(
                _(
                    "Closed match days contain execution and publication history. "
                    "Use Delete Match Day and confirm the impact before removing it."
                )
            )

        Schedule = (
            self.env["federation.schedule"].sudo().with_context(active_test=False)
        )
        schedules = Schedule.search([("matchday_id", "=", self.id)])
        reviews = (
            self.env["federation.schedule.review"]
            .sudo()
            .search([("schedule_id", "in", schedules.ids)])
        )
        publications = (
            self.env["federation.schedule.publication"]
            .sudo()
            .search([("schedule_id", "in", schedules.ids)])
        )
        slots = (
            self.env["federation.schedule.slot"]
            .sudo()
            .search([("matchday_id", "=", self.id)])
        )
        matches = (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    "|",
                    "|",
                    ("schedule_publication_id", "in", publications.ids),
                    ("published_slot_id", "in", slots.ids),
                    ("operational_slot_id", "in", slots.ids),
                ]
            )
        )

        self.sudo().write({"current_publication_id": False})
        matches.write(
            {
                "schedule_publication_id": False,
                "published_slot_id": False,
                "operational_slot_id": False,
            }
        )
        self.env["federation.matchday.deviation"].sudo().with_context(
            **{
                MATCHDAY_DESTRUCTIVE_DELETE_CONTEXT_KEY: MATCHDAY_DESTRUCTIVE_DELETE_TOKEN
            }
        ).search([("matchday_id", "=", self.id)]).unlink()
        self.env["federation.matchday.session"].sudo().with_context(
            **{
                MATCHDAY_DESTRUCTIVE_DELETE_CONTEXT_KEY: MATCHDAY_DESTRUCTIVE_DELETE_TOKEN
            }
        ).search([("matchday_id", "=", self.id)]).unlink()
        reviews.with_context(
            **{
                MATCHDAY_DESTRUCTIVE_DELETE_CONTEXT_KEY: MATCHDAY_DESTRUCTIVE_DELETE_TOKEN
            }
        ).unlink()
        publications.with_context(
            **{
                MATCHDAY_DESTRUCTIVE_DELETE_CONTEXT_KEY: MATCHDAY_DESTRUCTIVE_DELETE_TOKEN
            }
        ).unlink()

        related_schedules = Schedule.search(
            [
                "|",
                ("supersedes_id", "in", schedules.ids),
                ("superseded_by_id", "in", schedules.ids),
            ]
        )
        (schedules | related_schedules).write(
            {"supersedes_id": False, "superseded_by_id": False}
        )
        schedules.with_context(
            **{
                MATCHDAY_DESTRUCTIVE_DELETE_CONTEXT_KEY: MATCHDAY_DESTRUCTIVE_DELETE_TOKEN
            }
        ).unlink()

    def unlink(self):
        """Delete draft match days together with their mutable schedules.

        ``federation.schedule.matchday_id`` deliberately uses a restrictive
        foreign key so published schedule history cannot be orphaned. Draft
        schedules are disposable planning data, however, and should not make
        an otherwise deletable draft match day impossible to remove.
        """
        for matchday in self:
            if matchday.state == "closed":
                matchday._delete_closed_matchday_data()
            else:
                matchday._delete_restartable_schedules()
        return super().unlink()

    def action_open_closed_delete(self):
        self.ensure_one()
        self.env["federation.competition.role.assignment"].assert_role(
            self.edition_id, "matchday_manager", "competition_director"
        )
        if self.state != "closed":
            raise ValidationError(_("Only closed match days can be deleted here."))
        wizard = self.env["federation.matchday.delete.wizard"].create(
            {"matchday_id": self.id}
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Delete Closed Match Day"),
            "res_model": "federation.matchday.delete.wizard",
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

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
