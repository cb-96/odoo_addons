from collections import defaultdict
from datetime import timedelta

from odoo import _, fields, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from .operation_tasks import FederationOperationTaskPortal
from .portal_helpers import FederationPortalBase


class FederationOperationTaskPortalQoL(FederationOperationTaskPortal):
    """Extend the existing action-items controller without a duplicate route owner."""

    @http.route()
    def portal_my_action_items(self, scope="my", status="open", task_type=None, **kw):
        Task = request.env["federation.operation.task"].sudo()
        Task.sync_for_user(user=request.env.user)
        domain = Task._portal_get_domain(user=request.env.user)
        if status == "recent":
            domain += [
                ("state", "=", "done"),
                ("completed_on", ">=", fields.Datetime.now() - timedelta(days=7)),
            ]
        else:
            domain += [("state", "!=", "done")]
        if scope == "my":
            domain += [
                "|",
                ("assigned_user_id", "=", request.env.user.id),
                ("assigned_user_id", "=", False),
            ]
        allowed_types = dict(Task._fields["task_type"].selection)
        if task_type in allowed_types:
            domain += [("task_type", "=", task_type)]
        tasks = Task.search(domain)
        buckets = defaultdict(lambda: Task.browse())
        for task in tasks:
            bucket = task.work_bucket or "now"
            if (
                task.state != "done"
                and task.assigned_user_id
                and task.assigned_user_id != request.env.user
            ):
                bucket = "waiting"
            buckets[bucket] |= task
        representatives = request.env["federation.club.representative"].sudo().search([
            ("club_id", "in", request.env.user.portal_club_scope_ids.ids),
            ("is_current", "=", True),
            ("effective_user_id", "!=", False),
        ])
        return request.render(
            "sports_federation_portal.portal_my_operation_tasks",
            {
                "tasks": tasks,
                "buckets": buckets,
                "representatives": representatives,
                "active_scope": scope,
                "active_status": status,
                "active_type": task_type,
                "task_type_labels": allowed_types,
                "success": kw.get("success"),
                "error": kw.get("error"),
                "page_name": "my_action_items",
            },
        )


class FederationQoLPortal(FederationPortalBase):
    def _task_scope(self):
        Task = request.env["federation.operation.task"].sudo()
        return Task, Task._portal_get_domain(user=request.env.user)

    @http.route("/my/action-items/assign", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def assign_action_item(self, task_id, user_id, **kw):
        Task, domain = self._task_scope()
        task = Task.search(domain + [("id", "=", int(task_id))], limit=1)
        if not task:
            return self._render_access_denied()
        try:
            task.with_user(request.env.user).action_assign_user(int(user_id))
        except (AccessError, ValidationError) as error:
            return self._redirect_with_query("/my/action-items", error=str(error))
        return self._redirect_with_query("/my/action-items", success=_("Action reassigned."))

    @http.route("/my/milestones", type="http", auth="user", website=True)
    def portal_milestones(self, **kw):
        Task, domain = self._task_scope()
        Task.sync_for_user(user=request.env.user)
        tasks = Task.search(domain + [("state", "!=", "done"), ("deadline", "!=", False)])
        groups = defaultdict(list)
        today = fields.Date.context_today(Task)
        now = fields.Datetime.now()
        for task in tasks:
            due = fields.Datetime.context_timestamp(Task, task.deadline).date()
            if task.deadline < now:
                key = "Overdue"
            elif due <= today + timedelta(days=7):
                key = "Next 7 days"
            else:
                key = "Later"
            groups[key].append(task)
        return request.render("sports_federation_portal.portal_milestones", {"groups": groups, "page_name": "milestones"})

    @http.route("/federation/operations/bulk-registrations", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def bulk_registrations(self, registration_ids="", decision="", reason="", **kw):
        if not request.env.user.has_group("sports_federation_base.group_federation_manager"):
            raise AccessError(_("Tournament manager access is required."))
        ids = [int(value) for value in str(registration_ids).split(",") if value.strip().isdigit()]
        registrations = request.env["federation.tournament.registration"].sudo().browse(ids).exists()
        if not registrations or any(record.state != "submitted" for record in registrations):
            return self._redirect_with_query("/federation/operations/action-items", error=_("Select submitted registrations only."))
        if decision in ("return", "reject") and not reason.strip():
            return self._redirect_with_query("/federation/operations/action-items", error=_("A reason is required."))
        failures = []
        for record in registrations:
            try:
                if decision == "accept": record.action_confirm()
                elif decision == "return": record.action_return(reason.strip())
                elif decision == "reject": record.action_reject(reason.strip())
                else: raise ValidationError(_("Choose a valid bulk decision."))
            except ValidationError as error:
                failures.append(_("%(record)s: %(error)s") % {"record": record.display_name, "error": str(error)})
        if failures:
            return self._redirect_with_query("/federation/operations/action-items", error=" | ".join(failures))
        return self._redirect_with_query("/federation/operations/action-items", success=_("Selected registrations processed."))

    @http.route("/federation/operations/send-reminders", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def bulk_reminders(self, task_ids="", **kw):
        if not request.env.user.has_group("sports_federation_base.group_federation_manager"):
            raise AccessError(_("Tournament manager access is required."))
        ids = [int(value) for value in str(task_ids).split(",") if value.strip().isdigit()]
        tasks = request.env["federation.operation.task"].sudo().browse(ids).exists().filtered(lambda task: task.state != "done")
        for task in tasks.filtered("assigned_user_id"):
            task.activity_schedule("mail.mail_activity_data_todo", user_id=task.assigned_user_id.id, summary=task.name, note=task.next_step or task.blocking_reason)
        return self._redirect_with_query("/federation/operations/action-items", success=_("Reminders created."))

    @http.route("/my/rosters/<int:roster_id>/copy-lines", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def copy_roster_lines(self, roster_id, source_roster_id, **kw):
        Roster = request.env["federation.team.roster"]
        domain = Roster._portal_get_scope_domain(user=request.env.user)
        privilege = request.env["federation.portal.privilege"]
        target = privilege.portal_search_by_id(Roster, roster_id, domain, user=request.env.user)
        source = privilege.portal_search_by_id(Roster, int(source_roster_id), domain, user=request.env.user)
        if not target or not source:
            return self._render_access_denied()
        try:
            copied, skipped = target._portal_copy_eligible_lines(source, user=request.env.user)
        except ValidationError as error:
            return self._redirect_with_query(f"/my/rosters/{roster_id}", error=str(error))
        return self._redirect_with_query(f"/my/rosters/{roster_id}", success=_("%(copied)s player(s) copied; %(skipped)s skipped for review.") % {"copied": copied, "skipped": skipped})
