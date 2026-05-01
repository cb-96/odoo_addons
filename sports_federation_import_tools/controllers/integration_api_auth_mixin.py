from odoo.exceptions import AccessError


class FederationIntegrationApiAuthMixin:
    def _get_bearer_token(self, headers):
        """Extract a bearer token from the authorization header."""
        authorization = (headers.get("Authorization") or "").strip()
        if not authorization:
            return ""

        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            raise AccessError("Authorization headers must use the Bearer scheme.")
        return token.strip()

    def _get_credentials(self):
        """Return partner credentials from the allowed request headers."""
        request_proxy = self._request_proxy
        headers = request_proxy.httprequest.headers
        if request_proxy.params.get("partner_code") or request_proxy.params.get(
            "access_token"
        ):
            raise AccessError(
                "Partner credentials must be supplied via request headers only."
            )
        partner_code = (headers.get("X-Federation-Partner-Code") or "").strip()
        token = (headers.get("X-Federation-Partner-Token") or "").strip()
        if not token:
            token = self._get_bearer_token(headers)
        if not partner_code or not token:
            raise AccessError("Partner code and token are required in request headers.")
        return partner_code, token

    def _get_remote_addr(self):
        """Return the best-effort caller IP for integration throttling."""
        request_proxy = self._request_proxy
        headers = getattr(request_proxy.httprequest, "headers", {}) or {}
        forwarded_for = (headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
        remote_addr = (
            forwarded_for
            or (getattr(request_proxy.httprequest, "remote_addr", "") or "").strip()
        )
        return remote_addr or "unknown"

    def _get_rate_limit_subject(self):
        """Key partner traffic by partner code, then fall back to caller IP."""
        headers = getattr(self._request_proxy.httprequest, "headers", {}) or {}
        partner_code = (headers.get("X-Federation-Partner-Code") or "").strip()
        if partner_code:
            return f"partner:{partner_code}"
        return f"ip:{self._get_remote_addr()}"

    def _rate_limit_response(self, scope):
        """Return a 429 response when the caller exceeds the route limit."""
        decision = (
            self._request_proxy.env["federation.request.rate.limit"]
            .sudo()
            .consume(
                scope,
                self._get_rate_limit_subject(),
            )
        )
        if decision["allowed"]:
            return False
        return self._json_response(
            {
                "error": f"Too many requests. Retry after {decision['retry_after']} seconds.",
                "error_code": "retryable_delivery",
            },
            status=429,
            headers=[("Retry-After", str(decision["retry_after"]))],
        )

    def _authenticate(self, contract_code=None):
        """Authenticate the current request against the managed partner registry."""
        partner_code, token = self._get_credentials()
        return (
            self._request_proxy.env["federation.integration.partner"]
            .sudo()
            .authenticate_partner(
                partner_code,
                token,
                contract_code=contract_code,
            )
        )
