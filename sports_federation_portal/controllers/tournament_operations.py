from odoo import _, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from .portal_helpers import FederationPortalBase


class FederationTournamentOperationsPortal(FederationPortalBase):
    """Tournament-day operations board routes."""

    def _operations_error(self, error_type, message, hint=False):
        """Return a compact JSON-RPC error payload for the operations board."""
        payload = {
            "ok": False,
            "error": {
                "type": error_type,
                "message": message,
            },
        }
        if hint:
            payload["error"]["hint"] = hint
        return payload

    def _operations_resolve_tournament(self, tournament_id):
        """Resolve tournament access for page and JSON routes."""
        Tournament = request.env["federation.tournament"]
        try:
            tournament = Tournament._operations_get_tournament_for_user(
                tournament_id,
                user=request.env.user,
            )
        except AccessError:
            tournament = Tournament.browse([])
        if tournament:
            return tournament, False
        if not Tournament.sudo().browse(tournament_id).exists():
            return False, self._operations_error(
                "not_found", _("Tournament not found.")
            )
        return False, self._operations_error(
            "forbidden",
            _("You do not have access to this tournament operations page."),
        )

    def _operations_resolve_match(self, tournament, match_id):
        """Resolve one match inside the tournament board boundary."""
        Match = request.env["federation.match"]
        try:
            match = tournament._operations_get_match_for_user(
                match_id,
                user=request.env.user,
            )
        except AccessError:
            match = Match.browse([])
        if match:
            return match, False
        if not Match.sudo().search(
            [("id", "=", match_id), ("tournament_id", "=", tournament.id)],
            limit=1,
        ):
            return False, self._operations_error("not_found", _("Match not found."))
        return False, self._operations_error(
            "forbidden",
            _("You do not have access to this match from the operations board."),
        )

    @http.route(
        ["/sports/tournament/<int:tournament_id>/operations"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_tournament_operations_page(self, tournament_id, **kw):
        """Render the tournament operations page shell."""
        tournament, error = self._operations_resolve_tournament(tournament_id)
        if not tournament:
            if error["error"]["type"] == "not_found":
                self._raise_not_found()
            return self._render_access_denied()
        values = {
            "page_name": "tournament_operations",
            "tournament": tournament,
            "operations_load_path": f"/sports/tournament/{tournament.id}/operations/data",
            "operations_action_path_template": (
                f"/sports/tournament/{tournament.id}/operations/matches/__MATCH_ID__/action"
            ),
            "operations_poll_interval_ms": 60000,
        }
        return request.render(
            "sports_federation_portal.portal_tournament_operations_page",
            values,
        )

    @http.route(
        ["/sports/tournament/<int:tournament_id>/operations/data"],
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def portal_tournament_operations_data(self, tournament_id, **kw):
        """Return the full operations payload for one tournament."""
        tournament, error = self._operations_resolve_tournament(tournament_id)
        if not tournament:
            return error
        try:
            return {
                "ok": True,
                "payload": tournament._operations_get_payload(user=request.env.user),
            }
        except AccessError:
            return self._operations_error(
                "forbidden",
                _("You do not have access to this tournament operations page."),
            )

    @http.route(
        [
            "/sports/tournament/<int:tournament_id>/operations/matches/<int:match_id>/action"
        ],
        type="jsonrpc",
        auth="user",
        methods=["POST"],
    )
    def portal_tournament_operations_action(self, tournament_id, match_id, **kw):
        """Apply one server-side match action and return the refreshed payload."""
        tournament, error = self._operations_resolve_tournament(tournament_id)
        if not tournament:
            return error
        match, error = self._operations_resolve_match(tournament, match_id)
        if not match:
            return error
        try:
            message = tournament._operations_apply_action(
                match,
                kw.get("action"),
                values=kw,
                user=request.env.user,
            )
        except ValidationError as exc:
            return self._operations_error(
                "validation",
                (
                    str(exc.args[0])
                    if exc.args
                    else _("We could not complete that action.")
                ),
            )
        except AccessError:
            return self._operations_error(
                "forbidden",
                _("You do not have access to this match from the operations board."),
            )
        return {
            "ok": True,
            "message": message,
            "payload": tournament._operations_get_payload(user=request.env.user),
        }
