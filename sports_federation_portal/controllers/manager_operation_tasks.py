from collections import Counter
from datetime import timedelta

from odoo import fields

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request


class FederationManagerOperationTasks(http.Controller):
    """Tournament-manager control centre for operational blockers."""

    @staticmethod
    def _require_manager():
        if not request.env.user.has_group(
            "sports_federation_base.group_federation_manager"
        ):
            raise AccessError("Tournament manager access is required.")

    @http.route(
        "/federation/operations/action-items",
        type="http",
        auth="user",
        website=True,
    )
    def manager_action_items(self, **kw):
        self._require_manager()
        Task = request.env["federation.operation.task"].sudo()
        Task.sync_for_user(user=request.env.user)
        domain = [("audience", "=", "manager"), ("state", "!=", "done")]
        allowed_types = dict(Task._fields["task_type"].selection)
        task_type = kw.get("task_type")
        if task_type in allowed_types:
            domain.append(("task_type", "=", task_type))
        if kw.get("blocking") == "1":
            domain.append(("blocking", "=", True))
        if kw.get("club_id", "").isdigit():
            domain.append(("responsible_club_id", "=", int(kw["club_id"])))
        if kw.get("tournament_id", "").isdigit():
            domain.append(("tournament_id", "=", int(kw["tournament_id"])))
        if kw.get("assignee") == "me":
            domain.append(("assigned_user_id", "=", request.env.user.id))
        if kw.get("due") == "7":
            domain += [("deadline", "!=", False), ("deadline", "<=", fields.Datetime.now() + timedelta(days=7))]
        tasks = Task.search(domain)
        all_open = Task.search(
            [("audience", "=", "manager"), ("state", "!=", "done")]
        )
        counts = Counter(all_open.mapped("task_type"))
        return request.render(
            "sports_federation_portal.manager_operation_task_control_centre",
            {
                "tasks": tasks,
                "summary": {
                    "total": len(all_open),
                    "blocking": len(all_open.filtered("blocking")),
                    "urgent": len(all_open.filtered(lambda task: task.priority == "2")),
                    "overdue": len(all_open.filtered("is_overdue")),
                },
                "task_type_counts": counts,
                "task_type_labels": allowed_types,
                "active_task_type": task_type if task_type in allowed_types else False,
                "active_blocking": kw.get("blocking") == "1",
                "clubs": all_open.mapped("responsible_club_id"),
                "tournaments": all_open.mapped("tournament_id"),
                "active_filters": kw,
                "success": kw.get("success"), "error": kw.get("error"),
            },
        )
