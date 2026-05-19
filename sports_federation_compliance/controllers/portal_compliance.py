from urllib.parse import quote_plus

from odoo import http
from odoo.addons.sports_federation_base.exceptions import (
    AttachmentScanVerificationError,
)
from odoo.addons.portal.controllers.portal import CustomerPortal
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request


class FederationCompliancePortal(CustomerPortal):
    def _prepare_compliance_layout_values(self, **extra_values):
        """Build compliance template values on top of the shared portal layout."""
        values = self._prepare_portal_layout_values()
        values.update(extra_values)
        values.setdefault("page_name", "my_compliance")
        return values

    def _redirect_to_workspace(self, message):
        """Redirect to the compliance workspace with a user-facing message."""
        return request.redirect(f"/my/compliance?error={quote_plus(message)}")

    def _redirect_to_detail(self, requirement_id, target_model, target_id, message):
        """Redirect to a compliance detail page with a user-facing message."""
        return request.redirect(
            "/my/compliance/%s/%s/%s?error=%s"
            % (requirement_id, target_model, target_id, quote_plus(message))
        )

    def _get_workspace_entry(self, requirement_id, target_model, target_id):
        """Resolve one workspace entry only if it is still visible to the caller."""
        return request.env[
            "federation.document.requirement"
        ]._portal_get_workspace_entry_for_user(
            requirement_id=requirement_id,
            target_model=target_model,
            target_id=target_id,
            user=request.env.user,
        )

    @http.route(["/my/compliance"], type="http", auth="user", website=True)
    def portal_my_compliance(self, **kw):
        """Render the compliance workspace from the shared requirement status rules."""
        Requirement = request.env["federation.document.requirement"]
        workspace_entries = Requirement._portal_get_workspace_entries(
            user=request.env.user
        )
        values = self._prepare_compliance_layout_values(
            workspace_entries=workspace_entries,
            has_compliance_access=Requirement._portal_has_access(user=request.env.user),
            counts={
                "attention": len(
                    [
                        entry
                        for entry in workspace_entries
                        if entry["requires_attention"]
                    ]
                ),
                "in_review": len(
                    [
                        entry
                        for entry in workspace_entries
                        if entry["status_key"] == "submitted"
                    ]
                ),
                "approved": len(
                    [
                        entry
                        for entry in workspace_entries
                        if entry["status_key"] == "approved"
                    ]
                ),
            },
            success=kw.get("success"),
            error=kw.get("error"),
        )
        return request.render(
            "sports_federation_compliance.portal_my_compliance_workspace",
            values,
        )

    @http.route(
        ["/my/compliance/<int:requirement_id>/<path:target_model>/<int:target_id>"],
        type="http",
        auth="user",
        website=True,
    )
    def portal_my_compliance_detail(
        self, requirement_id, target_model, target_id, **kw
    ):
        """Render detail only while the requirement and target stay in user scope."""
        entry = self._get_workspace_entry(requirement_id, target_model, target_id)
        if not entry:
            return self._redirect_to_workspace(
                "This compliance item is no longer available in your workspace."
            )

        values = self._prepare_compliance_layout_values(
            compliance_entry=entry,
            success=kw.get("success"),
            error=kw.get("error"),
        )
        return request.render(
            "sports_federation_compliance.portal_my_compliance_detail",
            values,
        )

    @http.route(
        [
            "/my/compliance/<int:requirement_id>/<path:target_model>/<int:target_id>/submit"
        ],
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=False,
    )
    def portal_my_compliance_submit(
        self, requirement_id, target_model, target_id, **post
    ):
        """Validate CSRF manually and submit a multipart compliance upload safely.

        The route keeps `csrf=False` only because the payload is multipart; it
        still requires an explicit CSRF token before delegating to the model
        service that re-checks ownership and upload policy.
        """
        if not request.validate_csrf(post.get("csrf_token")):
            return self._redirect_to_detail(
                requirement_id,
                target_model,
                target_id,
                "Your session expired. Refresh the page and try again.",
            )

        entry = self._get_workspace_entry(requirement_id, target_model, target_id)
        if not entry:
            return self._redirect_to_workspace(
                "This compliance item is no longer available in your workspace."
            )

        redirect_url = entry["detail_url"]
        try:
            request.env["federation.document.submission"]._portal_submit_submission(
                entry["requirement"],
                entry["target"],
                values={
                    "issue_date": (post.get("issue_date") or "").strip() or False,
                    "expiry_date": (post.get("expiry_date") or "").strip() or False,
                    "notes": (post.get("notes") or "").strip() or False,
                },
                uploaded_files=request.httprequest.files.getlist("attachment"),
                user=request.env.user,
            )
        except (AccessError, ValidationError, AttachmentScanVerificationError) as error:
            return request.redirect(f"{redirect_url}?error={quote_plus(str(error))}")

        return request.redirect(
            f"{redirect_url}?success=Compliance+submission+sent+for+review"
        )
