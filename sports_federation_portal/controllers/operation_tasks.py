from odoo import http
from odoo.http import request

from .portal_helpers import FederationPortalBase


class FederationOperationTaskPortal(FederationPortalBase):
    """Club-facing readiness queue backed by operational projections."""

    @http.route("/my/action-items", type="http", auth="user", website=True)
    def portal_my_action_items(self, **kw):
        Task = request.env["federation.operation.task"].sudo()
        Task.sync_for_user(user=request.env.user)
        domain = Task._portal_get_domain(user=request.env.user)
        tasks = Task.search(domain + [("state", "!=", "done")])
        task_groups = {
            "overdue": tasks.filtered(lambda task: task.deadline and task.is_overdue),
            "blocking": tasks.filtered("blocking"),
            "waiting_federation": tasks.filtered(lambda task: task.waiting_on == "federation"),
            "mine": tasks.filtered(lambda task: task.assigned_user_id == request.env.user),
        }
        completed_steps = 4 - len(set(tasks.mapped("task_type")))
        journey_percent = max(0, min(100, int(completed_steps * 25)))
        return request.render(
            "sports_federation_portal.portal_my_operation_tasks",
            {
                "tasks": tasks,
                "task_groups": task_groups,
                "journey_percent": journey_percent,
                "page_name": "my_action_items",
            },
        )
