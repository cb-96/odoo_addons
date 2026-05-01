from urllib.parse import quote_plus

from odoo import fields, http
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request


class FederationOfficiatingPortal(http.Controller):
    def _raise_not_found(self):
        """Raise the framework 404 exception for hidden officiating resources."""
        raise request.not_found()

    @http.route(
        ["/my/referee-assignments", "/my/referee-assignments/page/<int:page>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_referee_assignments(self, page=1, filterby="upcoming", **kw):
        """Handle the portal my referee assignments flow."""
        Referee = request.env["federation.referee"].with_user(request.env.user).sudo()
        referee = Referee._portal_get_for_user(user=request.env.user)
        if not referee:
            return request.redirect("/my")

        Assignment = (
            request.env["federation.match.referee"].with_user(request.env.user).sudo()
        )
        domain = Assignment._portal_get_domain(user=request.env.user)
        filter_map = {
            "upcoming": [
                ("match_kickoff", "!=", False),
                ("state", "in", ("draft", "confirmed")),
            ],
            "pending": [("state", "=", "draft")],
            "history": [("state", "in", ("done", "cancelled"))],
            "all": [],
        }
        domain += filter_map.get(filterby, filter_map["upcoming"])

        total = Assignment.search_count(domain)
        pager = portal_pager(
            url="/my/referee-assignments",
            total=total,
            page=page,
            step=20,
            url_args={"filterby": filterby},
        )
        assignments = Assignment.search(
            domain,
            limit=20,
            offset=pager["offset"],
            order="match_kickoff asc, id asc",
        )
        values = {
            "referee": referee,
            "assignments": assignments,
            "pager": pager,
            "filterby": filterby,
            "page_name": "my_referee_assignments",
            "now": fields.Datetime.now(),
        }
        return request.render(
            "sports_federation_portal.portal_my_referee_assignments",
            values,
        )

    @http.route(
        ["/my/referee-assignments/<int:assignment_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_referee_assignment_detail(self, assignment_id, **kw):
        """Handle the portal my referee assignment detail flow."""
        Assignment = (
            request.env["federation.match.referee"].with_user(request.env.user).sudo()
        )
        assignment = Assignment.browse(assignment_id)
        try:
            if not assignment.exists():
                self._raise_not_found()
            assignment._portal_assert_access(user=request.env.user)
        except AccessError:
            self._raise_not_found()

        values = {
            "assignment": assignment,
            "page_name": "my_referee_assignments",
            "error": kw.get("error"),
            "success": kw.get("success"),
        }
        return request.render(
            "sports_federation_portal.portal_my_referee_assignment_detail",
            values,
        )

    @http.route(
        ["/my/referee-assignments/<int:assignment_id>/respond"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_my_referee_assignment_respond(
        self, assignment_id, action=None, response_note=None, **kw
    ):
        """Handle the portal my referee assignment respond flow."""
        Assignment = (
            request.env["federation.match.referee"].with_user(request.env.user).sudo()
        )
        assignment = Assignment.browse(assignment_id)
        try:
            if not assignment.exists():
                self._raise_not_found()
            assignment._portal_assert_access(user=request.env.user)
            if action == "confirm":
                assignment._portal_action_confirm(
                    user=request.env.user,
                    response_note=response_note,
                )
                message = "Assignment confirmed."
            elif action == "decline":
                assignment._portal_action_decline(
                    user=request.env.user,
                    response_note=response_note,
                )
                message = "Assignment declined."
            else:
                raise ValidationError("Choose a valid response action.")
        except AccessError:
            self._raise_not_found()
        except ValidationError as exc:
            return request.redirect(
                "/my/referee-assignments/%s?error=%s"
                % (assignment_id, quote_plus(str(exc)))
            )

        return request.redirect(
            "/my/referee-assignments/%s?success=%s"
            % (assignment_id, quote_plus(message))
        )
