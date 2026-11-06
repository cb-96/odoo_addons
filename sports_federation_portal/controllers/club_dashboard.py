"""Club representative home: stable club overview with contextual action badges."""
from odoo.http import request

from .portal_helpers import FederationPortalBase


class FederationClubDashboard(FederationPortalBase):
    def _prepare_portal_layout_values(self):
        values = super()._prepare_portal_layout_values()
        representative = values.get("federation_representative")
        if not representative:
            values["federation_club_dashboard"] = {}
            return values

        user = request.env.user
        clubs = representative.mapped("club_id")
        club_ids = clubs.ids
        Task = request.env["federation.operation.task"]
        Task.sync_for_user(user=user)
        privilege = request.env["federation.portal.privilege"]
        open_tasks = privilege.portal_search(
            Task,
            Task._portal_get_domain(user) + [("state", "!=", "done")],
            user=user,
        )
        task_counts = {}
        for task in open_tasks:
            task_counts[task.task_type] = task_counts.get(task.task_type, 0) + 1

        teams = privilege.portal_search(
            request.env["federation.team"],
            [("club_id", "in", club_ids), ("active", "=", True)],
            user=user,
        )
        roster_model = request.env["federation.team.roster"]
        rosters = privilege.portal_search(
            roster_model,
            roster_model._portal_get_scope_domain(user=user) + [("active", "=", True)],
            user=user,
        )
        editions = request.env["federation.portal.competition.queries"].visible_editions(
            user=user
        )
        values["federation_club_dashboard"] = {
            "teams": len(teams),
            "players": privilege.portal_search_count(
                request.env["federation.player"],
                [("club_id", "in", club_ids), ("active", "=", True)],
                user=user,
            ),
            "rosters": len(rosters),
            "competitions": len(editions),
            "tasks": len(open_tasks),
            "badges": {
                "teams": task_counts.get("registration", 0),
                "players": task_counts.get("parental_consent", 0),
                "rosters": task_counts.get("roster_readiness", 0),
                "preparation": task_counts.get("gameday_lineup", 0),
                "officials": task_counts.get("referee_duty", 0),
                "results": task_counts.get("result_review", 0),
            },
        }
        return values
