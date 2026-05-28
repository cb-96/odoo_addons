import json

from odoo.addons.sports_federation_base.models.failure_feedback import (
    build_failure_feedback,
)
from odoo.http import Response


class FederationIntegrationApiResponseMixin:
    def _json_response(self, payload, status=200, headers=None):
        """Build a JSON response with the shared integration content type."""
        return Response(
            json.dumps(payload),
            status=status,
            content_type="application/json; charset=utf-8",
            headers=headers or [],
        )

    def _json_error_response(
        self, status, error=None, detail=None, default_category="unexpected_bug"
    ):
        """Return a typed JSON error payload with sanitized operator detail."""
        failure_category, operator_message = build_failure_feedback(
            error=error,
            detail=detail,
            default_category=default_category,
        )
        return self._json_response(
            {
                "error": operator_message,
                "error_code": failure_category,
            },
            status=status,
        )
