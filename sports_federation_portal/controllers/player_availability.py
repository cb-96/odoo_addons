"""Optional player availability: ask players before a game day.

Controllers only parse input and render; scope checks and writes live in
``federation.player.availability.request`` portal commands.
"""

from odoo import _, http
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request

from .portal_helpers import FederationPortalBase

ANSWERS = ("yes", "maybe", "no")


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class FederationPlayerAvailabilityPortal(FederationPortalBase):
    def _availability_model(self):
        return request.env["federation.player.availability.request"]

    def _availability_render(self, template, values):
        layout = self._prepare_portal_layout_values()
        layout.update(values)
        layout.setdefault("success", request.params.get("success"))
        layout.setdefault("error", request.params.get("error"))
        return request.render(template, layout)

    @http.route(
        ["/my/availability"], type="http", auth="user", website=True, methods=["GET"]
    )
    def portal_availability(self, **kw):
        Request = self._availability_model()
        return self._availability_render(
            "sports_federation_portal.portal_player_availability",
            {
                "enabled": Request._portal_enabled(),
                "rows": Request._portal_upcoming(),
                "can_configure": bool(request.env.user.portal_club_scope_ids),
                "page_name": "player_availability",
            },
        )

    @http.route(
        ["/my/availability/new"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_availability_new(self, team_id=None, matchday_id=None, **kw):
        try:
            availability, sent = self._availability_model()._portal_create(
                _int(team_id), _int(matchday_id)
            )
        except AccessError:
            return self._render_access_denied()
        except (UserError, ValidationError) as error:
            return self._redirect_with_query("/my/availability", error=str(error))
        return self._redirect_with_query(
            "/my/availability/%s" % availability.id,
            success=_("%s player(s) received an email.", sent),
        )

    @http.route(
        ["/my/availability/<int:request_id>"],
        type="http",
        auth="user",
        website=True,
        methods=["GET"],
    )
    def portal_availability_detail(self, request_id, **kw):
        try:
            availability = self._availability_model()._portal_get(request_id)
        except AccessError:
            return self._render_access_denied()
        return self._availability_render(
            "sports_federation_portal.portal_player_availability_detail",
            {"availability": availability, "page_name": "player_availability"},
        )

    @http.route(
        ["/my/availability/<int:request_id>/answer"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_availability_answer(self, request_id, line_id=None, response=None, **kw):
        url = "/my/availability/%s" % request_id
        try:
            availability = self._availability_model()._portal_get(request_id)
            availability._portal_answer(_int(line_id), response)
        except AccessError:
            return self._render_access_denied()
        except ValidationError as error:
            return self._redirect_with_query(url, error=str(error))
        return self._redirect_with_query(url, success=_("Answer saved."))

    @http.route(
        ["/my/availability/<int:request_id>/remind"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_availability_remind(self, request_id, **kw):
        url = "/my/availability/%s" % request_id
        try:
            sent = self._availability_model()._portal_get(request_id)._portal_remind()
        except AccessError:
            return self._render_access_denied()
        except ValidationError as error:
            return self._redirect_with_query(url, error=str(error))
        return self._redirect_with_query(
            url, success=_("Reminder sent to %s player(s).", sent)
        )

    @http.route(
        ["/my/club/player-availability"],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
    )
    def portal_club_player_availability(self, club_id=None, enabled=None, **kw):
        try:
            club = request.env["federation.club"]._portal_set_player_availability(
                _int(club_id), enabled == "1"
            )
        except AccessError:
            return self._render_access_denied()
        message = (
            _("Player availability is on. Ask your players from Player availability.")
            if club.player_availability_enabled
            else _("Player availability is off.")
        )
        return self._redirect_with_query(
            "/my/club", club=club.id, success=message
        )


class FederationPlayerAvailabilityLink(http.Controller):
    """The personal link a player receives by email; no account needed."""

    @http.route(
        ["/availability/<string:token>"],
        type="http",
        auth="public",
        website=True,
        methods=["GET", "POST"],
        csrf=True,
        sitemap=False,
    )
    def player_availability_link(self, token, response=None, note=None, **kw):
        line = request.env["federation.player.availability"]._from_token(token)
        if not line:
            return request.render(
                "sports_federation_portal.player_availability_link_invalid",
                {},
                status=404,
            )
        error = saved = False
        if request.httprequest.method == "POST":
            if response not in ANSWERS:
                error = _("Choose Available, Maybe or Not available.")
            else:
                try:
                    line._record_response(response, note, by="player")
                    saved = True
                except ValidationError as exc:
                    error = str(exc)
        return request.render(
            "sports_federation_portal.player_availability_link",
            {
                "line": line,
                "availability": line.request_id,
                "open": line.request_id._is_open(),
                "saved": saved,
                "error": error,
            },
        )
