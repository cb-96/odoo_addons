import base64

from odoo import http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request

from .portal_helpers import FederationPortalBase


class FederationParentalApprovalPortal(FederationPortalBase):
    def _get_owned_player(self, player_id):
        clubs = self._get_portal_clubs()
        if not clubs:
            return request.env["federation.player"]
        try:
            player_id = int(player_id)
        except (TypeError, ValueError):
            return request.env["federation.player"]
        return request.env["federation.portal.privilege"].portal_search_by_id(
            request.env["federation.player"],
            player_id,
            domain=[("club_id", "in", clubs.ids)],
            user=request.env.user,
        )


    def _get_owned_approval(self, player, approval_id):
        try:
            approval_id = int(approval_id)
        except (TypeError, ValueError):
            return request.env["federation.player.parental.approval"]
        return request.env["federation.portal.privilege"].portal_search_by_id(
            request.env["federation.player.parental.approval"],
            approval_id,
            domain=[("player_id", "=", player.id)],
            user=request.env.user,
        )

    @http.route(
        "/my/players/<int:player_id>/parental-approvals",
        type="http", auth="user", website=True, methods=["GET"],
    )
    def portal_player_parental_approvals(self, player_id, **kw):
        player = self._get_owned_player(player_id)
        if not player:
            return self._render_access_denied()
        approvals = request.env["federation.portal.privilege"].portal_search(
            request.env["federation.player.parental.approval"],
            [("player_id", "=", player.id)],
            user=request.env.user,
            order="approval_date desc, id desc",
        )
        return request.render(
            "sports_federation_portal.portal_player_parental_approvals",
            {
                "page_name": "player_parental_approvals",
                "player": player,
                "approvals": approvals,
                "success": kw.get("success"),
                "error": kw.get("error"),
            },
        )


    @http.route(
        "/my/players/<int:player_id>/parental-approvals/<int:approval_id>/download",
        type="http", auth="user", website=True, methods=["GET"],
    )
    def portal_player_parental_approval_download(self, player_id, approval_id, **kw):
        player = self._get_owned_player(player_id)
        if not player:
            return self._render_access_denied()
        approval = self._get_owned_approval(player, approval_id)
        if not approval or not approval.approval_document:
            return request.not_found()
        filename = (approval.approval_document_filename or "parental-approval.pdf").replace("\r", "").replace("\n", "")
        return request.make_response(
            base64.b64decode(approval.approval_document),
            headers=[
                ("Content-Type", "application/octet-stream"),
                ("Content-Disposition", 'attachment; filename="%s"' % filename.replace('"', "")),
                ("X-Content-Type-Options", "nosniff"),
                ("Cache-Control", "private, no-store"),
            ],
        )

    @http.route(
        "/my/players/<int:player_id>/parental-approvals/upload",
        type="http", auth="user", website=True, methods=["POST"], csrf=True,
    )
    def portal_player_parental_approval_upload(self, player_id, **post):
        player = self._get_owned_player(player_id)
        if not player:
            return self._render_access_denied()
        upload = request.httprequest.files.get("approval_document")
        try:
            request.env[
                "federation.player.parental.approval"
            ]._portal_create_parental_approval(
                player,
                {
                    "guardian_name": post.get("guardian_name"),
                    "guardian_email": post.get("guardian_email"),
                    "approval_date": post.get("approval_date"),
                    "valid_until": post.get("valid_until"),
                    "notes": post.get("notes"),
                },
                upload,
                user=request.env.user,
            )
        except (AccessError, ValidationError, ValueError) as error:
            return self._redirect_with_query(
                f"/my/players/{player.id}/parental-approvals", error=str(error)
            )
        return self._redirect_with_query(
            f"/my/players/{player.id}/parental-approvals",
            success="Parental approval uploaded and sent for federation review.",
        )
