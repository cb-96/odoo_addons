"""Open and close game days without manual ceremony.

A published game day opens on its date (or as soon as someone starts entering
results), and closes as soon as every published match has an official result
and no incident is unresolved.  The governed match-day commands still perform
the transition, integrity checks and audit; only the trigger is automatic.
Anything unusual (missing publication, open incidents, unplayed matches) keeps
the day as it is and remains visible in the planner and match-day readiness.
"""
import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

AUTOMATION_CONTEXT = "matchday_automation"


class FederationMatchdayCommandsAutomation(models.AbstractModel):
    _inherit = "federation.matchday.commands"

    def _resolve(self, matchday_id):
        # Automation runs as the superuser from the scheduler or from a
        # completed result approval; there is no competition role to assert.
        if self.env.su and self.env.context.get(AUTOMATION_CONTEXT):
            matchday = self.env["federation.matchday"].browse(int(matchday_id)).exists()
            if not matchday:
                raise ValidationError(_("The match day no longer exists."))
            return matchday
        return super()._resolve(matchday_id)


class FederationMatchdayAutomation(models.Model):
    _inherit = "federation.matchday"

    def _automation_commands(self):
        return (
            self.env["federation.matchday.commands"]
            .sudo()
            .with_context(**{AUTOMATION_CONTEXT: True})
        )

    def _auto_open_if_due(self):
        """Open published game days whose date has arrived."""
        today = fields.Date.context_today(self)
        opened = self.browse()
        for day in self:
            if day.state != "scheduled" or not day.date or day.date > today:
                continue
            if day.readiness_state != "ready":
                continue
            try:
                with self.env.cr.savepoint():
                    day._automation_commands().open_matchday(day.id)
                opened |= day
            except (AccessError, UserError, ValidationError) as error:
                _logger.info("Game day %s not opened automatically: %s", day.id, error)
        return opened

    def _ready_to_close_automatically(self):
        self.ensure_one()
        day = self.sudo()
        if day.state != "open" or not day.active_session_id:
            return False
        publication = day.current_publication_id
        if not publication:
            return False
        matches = self.env["federation.match"].sudo().search(
            [("schedule_publication_id", "=", publication.id)]
        )
        if not matches:
            return False
        for match in matches:
            if match.state == "cancelled":
                continue
            if match.state != "done" or match.result_state != "approved":
                return False
        return not self.env["federation.matchday.incident"].sudo().search_count(
            [("matchday_id", "=", day.id), ("resolved", "=", False)]
        )

    def _auto_close_if_complete(self):
        """Close open game days once every match result is official."""
        closed = self.browse()
        for day in self:
            if not day._ready_to_close_automatically():
                continue
            try:
                with self.env.cr.savepoint():
                    day._automation_commands().close_matchday(
                        day.id,
                        close_note=_("Closed automatically: every match has an official result."),
                    )
                closed |= day
            except (AccessError, UserError, ValidationError) as error:
                _logger.info("Game day %s not closed automatically: %s", day.id, error)
        return closed

    @api.model
    def _cron_matchday_automation(self):
        today = fields.Date.context_today(self)
        self.search([("state", "=", "scheduled"), ("date", "<=", today)])._auto_open_if_due()
        self.search([("state", "=", "open")])._auto_close_if_complete()
        return True

    def action_open_focus_results(self):
        """Entering results on the day itself starts the game day."""
        self.ensure_one()
        if self.state == "scheduled":
            self.check_access("read")
            self._auto_open_if_due()
        return super().action_open_focus_results()


class FederationMatchAutomation(models.Model):
    _inherit = "federation.match"

    def _complete_after_result_approval(self):
        result = super()._complete_after_result_approval()
        days = self.sudo().mapped("schedule_publication_id.matchday_id")
        if days:
            days._auto_close_if_complete()
        return result
