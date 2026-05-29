import re

from odoo.exceptions import ValidationError
from odoo.http import request


class FederationRequestSecurityMixin:
    """Shared request-level security helpers for controller routes."""

    _IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")

    def _security_request_proxy(self):
        """Return the active request proxy, supporting controller test doubles."""
        return getattr(self, "_request_proxy", request)

    def _validate_manual_csrf(self, csrf_token):
        """Validate a CSRF token for routes that intentionally disable framework CSRF."""
        request_proxy = self._security_request_proxy()
        token = (csrf_token or "").strip()
        if not token or not request_proxy.validate_csrf(token):
            raise ValidationError(
                "Your session expired. Refresh the page and try again."
            )
        return True

    def _get_idempotency_key(self, header_name="X-Federation-Idempotency-Key"):
        """Return a validated idempotency key header when present."""
        request_proxy = self._security_request_proxy()
        header_value = (
            request_proxy.httprequest.headers.get(header_name) or ""
        ).strip()
        if not header_value:
            return False
        if not self._IDEMPOTENCY_RE.match(header_value):
            raise ValidationError(
                "Idempotency keys must be 1-128 chars and use only letters, digits, and _.:-"
            )
        return header_value
