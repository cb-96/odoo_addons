import json

from odoo.addons.sports_federation_base.correlation import ensure_correlation_id
from odoo.addons.sports_federation_base.models.failure_feedback import (
    build_failure_feedback,
)
from odoo.http import Response


class FederationIntegrationApiResponseMixin:
    def _response_correlation_id(self, correlation_id=False):
        request_proxy = getattr(self, "_request_proxy", None)
        env = getattr(request_proxy, "env", None)
        return ensure_correlation_id(env, correlation_id)

    def _json_response(self, payload, status=200, headers=None):
        """Build a JSON response with the shared integration content type."""
        correlation_id = self._response_correlation_id(
            payload.get("correlation_id") if isinstance(payload, dict) else False
        )
        if isinstance(payload, dict):
            payload = dict(payload)
            payload.setdefault("correlation_id", correlation_id)
        normalized_headers = list(headers or [])
        if not any(
            name == "X-Federation-Correlation-Id" for name, _ in normalized_headers
        ):
            normalized_headers.append(("X-Federation-Correlation-Id", correlation_id))
        return Response(
            json.dumps(payload),
            status=status,
            content_type="application/json; charset=utf-8",
            headers=normalized_headers,
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
        correlation_id = self._response_correlation_id()
        return self._json_response(
            {
                "error": operator_message,
                "error_code": failure_category,
                "correlation_id": correlation_id,
            },
            status=status,
        )
