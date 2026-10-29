from urllib.parse import urlencode
from odoo import _, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request
from odoo.addons.sports_federation_portal.controllers.officiating import (
    FederationOfficiatingPortal,
)


class Workspace(FederationOfficiatingPortal):
    def _owned(self, assignment_id):
        # Elevation is constrained to the current individual's assignment before any
        # fields are rendered.
        a = (
            request.env["federation.match.referee"]
            .sudo()
            .search(
                [
                    ("id", "=", assignment_id),
                    ("referee_id.user_id", "=", request.env.uid),
                    ("fixture_id", "!=", False),
                    ("publication_id", "!=", False),
                ],
                limit=1,
            )
        )
        if not a:
            raise request.not_found()
        return a

    @http.route(
        ["/my/duty-assignments"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def assignments(self, filterby="current", page=1, **kw):
        filterby = filterby if filterby in ("current", "history") else "current"
        try:
            page = max(1, int(page))
        except (ValueError, TypeError):
            page = 1
        model = request.env["federation.match.referee"].sudo()
        domain = [
            ("referee_id.user_id", "=", request.env.uid),
            ("fixture_id", "!=", False),
            ("publication_id", "!=", False),
        ]
        if filterby == "current":
            domain += [
                ("is_current_publication", "=", True),
                ("state", "not in", ["done", "cancelled"]),
            ]
        rows = model.search(
            domain, order="match_kickoff,id", offset=(page - 1) * 40, limit=41
        )
        return request.render(
            "sports_federation_duty_coverage.my_assignments",
            {
                "assignments": rows[:40],
                "more": len(rows) > 40,
                "page": page,
                "filterby": filterby,
                "page_name": "duty_assignments",
            },
        )

    @http.route(
        ["/my/duty-assignments/<int:assignment_id>"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def detail(self, assignment_id, filterby="current", **kw):
        a = self._owned(assignment_id)
        return request.render(
            "sports_federation_duty_coverage.assignment_detail",
            {
                "assignment": a,
                "signature": a._coverage_signature(),
                "filterby": "history" if filterby == "history" else "current",
                "error": kw.get("error"),
                "success": kw.get("success"),
                "page_name": "duty_assignments",
            },
        )

    @http.route(
        ["/my/duty-assignments/<int:assignment_id>/respond"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def respond(
        self,
        assignment_id,
        action=None,
        signature=None,
        response_note=None,
        filterby="current",
        **kw
    ):
        a = self._owned(assignment_id)
        query = {"filterby": "history" if filterby == "history" else "current"}
        try:
            with request.env.cr.savepoint():
                a._coverage_lock()
                if not signature or signature != a._coverage_signature():
                    raise ValidationError(
                        _(
                            (
                                "Schedule changed. Review the current "
                                "assignment before "
                                "responding."
                            )
                        )
                    )
                if action == "confirm":
                    a._portal_action_confirm(
                        user=request.env.user, response_note=response_note
                    )
                elif action == "decline":
                    a._portal_action_decline(
                        user=request.env.user, response_note=response_note
                    )
                else:
                    raise ValidationError(_("Choose accept or decline."))
                query["success"] = _(
                    "Response recorded. Assignment alone is not attendance."
                )
        except (AccessError, ValidationError) as exc:
            query["error"] = str(exc)
        return request.redirect(
            "/my/duty-assignments/%s?%s" % (a.id, urlencode(query)), code=303
        )

    # Keep existing links functional; old response forms must not accept a stale
    # schedule silently.
    @http.route()
    def portal_my_referee_assignments(self, page=1, filterby="upcoming", **kw):
        return request.redirect(
            "/my/duty-assignments?"
            + urlencode(
                {
                    "filterby": "history" if filterby == "all" else "current",
                    "page": page,
                }
            )
        )

    @http.route()
    def portal_my_referee_assignment_detail(self, assignment_id, **kw):
        self._owned(assignment_id)
        return request.redirect("/my/duty-assignments/%s" % assignment_id)

    @http.route()
    def portal_my_referee_assignment_respond(
        self, assignment_id, action=None, response_note=None, **kw
    ):
        self._owned(assignment_id)
        return request.redirect(
            "/my/duty-assignments/%s?%s"
            % (
                assignment_id,
                urlencode(
                    {"error": _("Review the new assignment page before responding.")}
                ),
            ),
            code=303,
        )
