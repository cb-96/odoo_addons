from collections import defaultdict
from odoo import _, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request
from odoo.addons.sports_federation_portal.controllers.qol import FederationOperationTaskPortalQoL
from odoo.addons.sports_federation_portal.controllers.roster_helpers import FederationRosterPortalBase
from odoo.addons.sports_federation_portal.controllers.manager_operation_tasks import FederationManagerOperationTasks
from ..journey_navigation import return_url, reviewer_can_act, safe_destination


class RoleJourneys(FederationRosterPortalBase):
    @http.route("/my/work", type="http", auth="user", website=True, methods=["GET"])
    def role_home(self, **kw):
        user = request.env.user
        task_model = request.env["federation.operation.task"].with_context(
            journey_viewer_id=user.id
        )
        has_club_access = bool(task_model._portal_club_ids(user))
        if has_club_access:
            task_model.sync_for_user(user=user)
        tasks = request.env["federation.portal.privilege"].portal_search(task_model, task_model._portal_get_domain(user) + [("state", "!=", "done")], user=user)
        referee = request.env["federation.referee"]._portal_get_for_user(user=user)
        return request.render("sports_federation_portal.role_home", {
            "tasks": tasks, "club_access": has_club_access,
            "official_access": bool(referee),
            "planner_access": user.has_group("sports_federation_competition_core.group_competition_administrator"),
            "reviewer_access": user.has_group("sports_federation_result_control.group_result_validator") or user.has_group("sports_federation_result_control.group_result_approver"),
            "manager_access": user.has_group("sports_federation_base.group_federation_manager"),
            "page_name": "role_work", "journey_user_id": user.id,
        })

    @http.route("/my/work/context", type="http", auth="user", methods=["GET"])
    def journey_context(self, **kw):
        response = request.make_json_response({"user_id": request.env.user.id})
        response.headers["Cache-Control"] = "no-store"
        return response

    @http.route("/my/work/reviews", type="http", auth="user", website=True, methods=["GET"])
    def review_work(self, **kw):
        user = request.env.user
        states = []
        if user.has_group("sports_federation_result_control.group_result_validator"):
            states.append("submitted")
        if user.has_group("sports_federation_result_control.group_result_approver"):
            states.append("verified")
        if not states:
            return self._render_access_denied()
        # Read as the actual user: record rules and command-owned approval checks remain authoritative.
        matches = request.env["federation.match"].search(
            [("result_state", "in", states)], limit=100, order="id desc"
        )
        matches = matches.filtered(lambda match: self._can_review_match(match, user))
        return request.render("sports_federation_portal.review_work", {"matches": matches})

    @staticmethod
    def _can_review_match(match, user):
        edition = match._competition_workflow_edition()
        return reviewer_can_act(
            match.result_state,
            user.id,
            match.result_submitted_by_id.id or False,
            match.result_verified_by_id.id or False,
            self_verification_allowed=edition.result_self_verification_allowed,
            self_approval_allowed=edition.result_self_approval_allowed,
        )

    @http.route("/my/work/tasks/<int:task_id>/open", type="http", auth="user", website=True, methods=["GET"])
    def open_task(self, task_id, **kw):
        user = request.env.user
        model = request.env["federation.operation.task"].with_context(
            journey_viewer_id=user.id
        )
        model.sync_for_user(user=user)
        task = request.env["federation.portal.privilege"].portal_search(model, model._portal_get_domain(user) + [("id", "=", task_id)], user=user, limit=1)
        if not task:
            return self._render_access_denied()
        if task.state == "done":
            return request.redirect(return_url("club", kw))
        if task.journey_status == "unavailable" or not safe_destination(task.action_url):
            return request.redirect(return_url("club", kw))
        # Destination controllers enforce current source ownership; this bridge never mutates it.
        return request.redirect(task.action_url)

    @http.route("/my/work/registrations/<int:registration_id>", type="http", auth="user", website=True, methods=["GET"])
    def missing_roster(self, registration_id, **kw):
        model = request.env["federation.team.roster"]
        try:
            registration = model._portal_assert_registration_access(
                request.env["federation.season.registration"].browse(registration_id), user=request.env.user)
            if registration.state != "confirmed":
                raise ValidationError(_("The registration must be confirmed before roster creation."))
            roster = model._portal_get_primary_roster_for_registration(registration, user=request.env.user)
        except (AccessError, ValidationError):
            return self._render_access_denied()
        if roster:
            return request.redirect("/my/rosters/%s" % roster.id)
        return request.render("sports_federation_portal.missing_roster", {
            "registration": registration, "page_name": "create_roster", "journey_user_id": request.env.user.id,
        })


class JourneyInbox(FederationOperationTaskPortalQoL):
    @http.route()
    def portal_my_action_items(self, scope="my", status="open", task_type=None, **kw):
        scope = scope if scope in ("my", "club") else "my"
        status = status if status in ("open", "recent") else "open"
        response = super().portal_my_action_items(scope=scope, status=status, task_type=task_type, **kw)
        if getattr(response, "qcontext", None) is not None:
            tasks = response.qcontext.get("tasks")
            if tasks is not None:
                tasks = tasks.with_context(journey_viewer_id=request.env.user.id)
                buckets = defaultdict(lambda: tasks.browse())
                for task in tasks:
                    bucket = "waiting" if task.journey_status in ("waiting", "unavailable") else task.work_bucket or "now"
                    if task.state != "done" and task.assigned_user_id and task.assigned_user_id != request.env.user:
                        bucket = "waiting"
                    buckets[bucket] |= task
                waiting_entries = request.env["federation.operation.task"]._journey_waiting_entries(user=request.env.user)
                if status == "recent" or task_type not in (None, "", "registration"):
                    waiting_entries = waiting_entries.browse()
                response.qcontext.update(buckets=buckets, journey_user_id=request.env.user.id,
                                         journey_waiting_entries=waiting_entries,
                                         tasks=tasks)
        return response


class JourneyManagerQueue(FederationManagerOperationTasks):
    @http.route()
    def manager_action_items(self, **kw):
        # Preserve the existing route owner and all its role/filter checks.
        response = super().manager_action_items(**kw)
        response.template = "sports_federation_portal.manager_queue"
        return response
