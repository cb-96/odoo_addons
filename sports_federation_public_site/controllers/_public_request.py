import json
from urllib.parse import quote_plus

from odoo.http import Response, request
from werkzeug.exceptions import NotFound


class PublicRequestInfrastructureMixin:
    """Framework-level response, resolution and throttling helpers.

    Domain-specific route orchestration stays in the public controller. Keeping
    these concerns separate makes privilege and publication review smaller.
    """

    def _raise_not_found(self):
        raise NotFound()

    def _make_json_response(self, payload, status=200, headers=None):
        make_json_response = getattr(request, "make_json_response", None)
        if make_json_response:
            return make_json_response(payload, status=status, headers=headers)
        return Response(json.dumps(payload), status=status, headers=headers or [], content_type="application/json; charset=utf-8")

    def _resolve_tournament(self, tournament_slug=None, tournament_id=None, tournament=False, public_access=None):
        Tournament = request.env["federation.tournament"]
        public_domain = self._build_tournament_public_domain(public_access)
        if tournament:
            return Tournament.sudo().search([("id", "=", tournament.id)] + public_domain, limit=1)
        if tournament_id:
            return Tournament.sudo().search([("id", "=", int(tournament_id))] + public_domain, limit=1)
        if tournament_slug:
            return Tournament.resolve_public_slug(tournament_slug, extra_domain=public_domain)
        return Tournament.browse([])

    def _resolve_team(self, team_slug, public_access=None):
        return request.env["federation.team"].resolve_public_slug(team_slug, extra_domain=self._build_team_public_domain(public_access))

    def _canonical_redirect(self, record, slug_value, path_getter):
        return request.redirect(path_getter()) if slug_value != record.get_public_slug_value() else None

    def _get_request_user_clubs(self):
        ClubRep = request.env.get("federation.club.representative")
        if ClubRep is None:
            return request.env["federation.club"].browse([])
        return ClubRep.sudo()._get_clubs_for_user(user=request.env.user)

    def _redirect_with_error(self, path, message):
        return request.redirect(f"{path}?error={quote_plus(message)}")

    def _get_rate_limit_subject(self):
        headers = getattr(request.httprequest, "headers", {}) or {}
        forwarded_for = (headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
        remote_addr = forwarded_for or (getattr(request.httprequest, "remote_addr", "") or "").strip()
        return f"ip:{remote_addr or 'unknown'}"

    def _rate_limit_response(self, scope):
        decision = request.env["federation.request.rate.limit"].sudo().consume(scope, self._get_rate_limit_subject())
        if decision["allowed"]:
            return False
        return self._make_json_response({"error": f"Too many requests. Retry after {decision['retry_after']} seconds.", "error_code": "retryable_delivery"}, status=429, headers=[("Retry-After", str(decision["retry_after"]))])
