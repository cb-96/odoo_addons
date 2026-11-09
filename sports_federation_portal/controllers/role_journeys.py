from collections import defaultdict
from odoo import _, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request
from odoo.addons.sports_federation_portal.controllers.qol import (
    FederationOperationTaskPortalQoL,
)
from odoo.addons.sports_federation_portal.controllers.roster_helpers import (
    FederationRosterPortalBase,
)
from odoo.addons.sports_federation_portal.controllers.manager_operation_tasks import (
    FederationManagerOperationTasks,
)
from ..journey_navigation import return_url, reviewer_can_act, safe_destination


class RoleJourneys(FederationRosterPortalBase):
    """Role work reached from the portal overview (``/my``).

    The overview itself is rendered by ``home``; these routes are the lists and
    bridges its sections link to.
    """

    @http.route("/my/journey-context", type="http", auth="user", methods=["GET"])
    def journey_context(self, **kw):
        response = request.make_json_response(
            {"user_id": request.env.user.id, "database": request.env.cr.dbname}
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @http.route(
        "/my/result-reviews", type="http", auth="user", website=True, methods=["GET"]
    )
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
            [("result_state", "in", states)]
            + request.env["federation.portal.archive.scope"].exclusion_domain(
                "federation.match"
            ),
            limit=100,
            order="id desc",
        )
        matches = matches.filtered(lambda match: self._can_review_match(match, user))
        return request.render(
            "sports_federation_portal.review_work", {"matches": matches}
        )

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

    @http.route(
        "/my/action-items/<int:task_id>/open",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def open_task(self, task_id, **kw):
        user = request.env.user
        model = request.env["federation.operation.task"].with_context(
            journey_viewer_id=user.id
        )
        model.sync_for_user(user=user)
        task = request.env["federation.portal.privilege"].portal_search(
            model,
            model._portal_get_domain(user) + [("id", "=", task_id)],
            user=user,
            limit=1,
        )
        if not task:
            return self._render_access_denied()
        if task.journey_status == "unavailable" or not safe_destination(
            task.action_url
        ):
            return request.redirect(return_url("club", kw))
        # Destination controllers enforce current source ownership; this bridge never mutates it.
        return request.redirect(task.action_url)

    @http.route(
        "/my/season-registrations/<int:registration_id>/roster",
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def missing_roster(self, registration_id, **kw):
        model = request.env["federation.team.roster"]
        try:
            registration = model._portal_assert_registration_access(
                request.env["federation.season.registration"].browse(registration_id),
                user=request.env.user,
            )
            if registration.state != "confirmed":
                raise ValidationError(
                    _("The registration must be confirmed before roster creation.")
                )
            roster = model._portal_get_primary_roster_for_registration(
                registration, user=request.env.user
            )
        except (AccessError, ValidationError):
            return self._render_access_denied()
        if roster:
            return request.redirect("/my/rosters/%s" % roster.id)
        return request.render(
            "sports_federation_portal.missing_roster",
            {
                "registration": registration,
                "page_name": "create_roster",
                "journey_user_id": request.env.user.id,
            },
        )


class RetiredWorkRoutes(http.Controller):
    """Permanent redirects for bookmarks of the retired ``/my/work`` pages.

    ``/my/work`` was the role switchboard; the portal overview (``/my``) now
    shows every role in its own section. Only redirects remain here.
    """

    @http.route(["/my/work"], type="http", auth="user", methods=["GET"])
    def retired_work_home(self, **kw):
        return request.redirect("/my", code=301)

    @http.route(["/my/work/reviews"], type="http", auth="user", methods=["GET"])
    def retired_review_work(self, **kw):
        return request.redirect("/my/result-reviews", code=301)

    @http.route(
        ["/my/work/tasks/<int:task_id>/open"],
        type="http",
        auth="user",
        methods=["GET"],
    )
    def retired_open_task(self, task_id, **kw):
        return request.redirect("/my/action-items/%s/open" % task_id, code=301)

    @http.route(
        ["/my/work/registrations/<int:registration_id>"],
        type="http",
        auth="user",
        methods=["GET"],
    )
    def retired_missing_roster(self, registration_id, **kw):
        return request.redirect(
            "/my/season-registrations/%s/roster" % registration_id, code=301
        )


class JourneyInbox(FederationOperationTaskPortalQoL):
    @http.route()
    def portal_my_action_items(self, scope="my", status="open", task_type=None, **kw):
        scope = scope if scope in ("my", "club") else "my"
        status = status if status in ("open", "recent") else "open"
        response = super().portal_my_action_items(
            scope=scope, status=status, task_type=task_type, **kw
        )
        if getattr(response, "qcontext", None) is not None:
            tasks = response.qcontext.get("tasks")
            if tasks is not None:
                tasks = tasks.with_context(journey_viewer_id=request.env.user.id)
                buckets = defaultdict(lambda: tasks.browse())
                for task in tasks:
                    bucket = (
                        "waiting"
                        if task.journey_status in ("waiting", "unavailable")
                        else task.work_bucket or "now"
                    )
                    if (
                        task.state != "done"
                        and task.assigned_user_id
                        and task.assigned_user_id != request.env.user
                    ):
                        bucket = "waiting"
                    buckets[bucket] |= task
                waiting_entries = request.env[
                    "federation.operation.task"
                ]._journey_waiting_entries(user=request.env.user)
                if status == "recent" or task_type not in (None, "", "registration"):
                    waiting_entries = waiting_entries.browse()
                response.qcontext.update(
                    buckets=buckets,
                    journey_user_id=request.env.user.id,
                    journey_waiting_entries=waiting_entries,
                    tasks=tasks,
                )
        return response


class JourneyManagerQueue(FederationManagerOperationTasks):
    @http.route()
    def manager_action_items(self, **kw):
        # Preserve the existing route owner and all its role/filter checks.
        response = super().manager_action_items(**kw)
        response.template = "sports_federation_portal.manager_queue"
        return response
