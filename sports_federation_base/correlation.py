import re
from uuid import uuid4

from odoo.http import request

_CORRELATION_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")


def normalize_correlation_id(value=False):
    """Return a normalized correlation id or False when absent/invalid."""
    candidate = str(value or "").strip()
    if not candidate:
        return False
    if not _CORRELATION_RE.match(candidate):
        return False
    return candidate


def get_request_correlation_id(header_name="X-Federation-Correlation-Id"):
    """Read a correlation id from the current HTTP request headers when available."""
    try:
        request_proxy = request
        httprequest = getattr(request_proxy, "httprequest", None)
    except RuntimeError:
        return False
    headers = getattr(httprequest, "headers", {}) or {}
    return normalize_correlation_id(headers.get(header_name))


def ensure_correlation_id(env=None, value=False):
    """Return a stable correlation id from explicit value, context, header, or a fresh id."""
    normalized = normalize_correlation_id(value)
    if normalized:
        return normalized

    if env is not None:
        context_value = normalize_correlation_id(
            (getattr(env, "context", {}) or {}).get("federation_correlation_id")
        )
        if context_value:
            return context_value

    request_value = get_request_correlation_id()
    if request_value:
        return request_value

    return uuid4().hex[:12]
