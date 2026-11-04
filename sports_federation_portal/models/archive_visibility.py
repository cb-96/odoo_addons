"""Apply the archived-competition exclusion to tasks and archive actions."""
from odoo import api, models


class OperationTaskArchiveVisibility(models.Model):
    _inherit = "federation.operation.task"

    @api.model
    def _portal_get_domain(self, user=None):
        # Also hides tasks closed because their competition was archived from
        # the "completed recently" part of the portal.
        return super()._portal_get_domain(user=user) + self.env[
            "federation.portal.archive.scope"
        ].exclusion_domain(self._name)


class CompetitionEditionArchiveTasks(models.Model):
    _inherit = "federation.competition.edition"

    def write(self, values):
        result = super().write(values)
        if "active" in values and not values["active"]:
            scope = self.env["federation.portal.archive.scope"]
            divisions = self.with_context(active_test=False).mapped("tournament_ids")
            scope.close_tasks_for_divisions(divisions.ids)
        return result


class TournamentArchiveTasks(models.Model):
    _inherit = "federation.tournament"

    def write(self, values):
        result = super().write(values)
        if "active" in values and not values["active"]:
            self.env["federation.portal.archive.scope"].close_tasks_for_divisions(self.ids)
        return result
