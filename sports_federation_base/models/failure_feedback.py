import re

from odoo.exceptions import AccessError, UserError, ValidationError

FAILURE_CATEGORY_SELECTION = [
    ("retryable_delivery", "Retryable Delivery Failure"),
    ("access_denied", "Access Or Authentication"),
    ("configuration_error", "Configuration Error"),
    ("data_validation", "Data Validation"),
    ("operator_input", "Operator Input"),
    ("unexpected_bug", "Unexpected Defect"),
]

FAILURE_CATEGORY_LABELS = dict(FAILURE_CATEGORY_SELECTION)

_TRACEBACK_MARKERS = (
    "traceback",
    ' file "',
    "odoo.addons",
    "psycopg",
    "sqlalchemy",
)
_TRANSIENT_KEYWORDS = (
    "timeout",
    "temporarily unavailable",
    "temporary failure",
    "connection reset",
    "connection refused",
    "connection aborted",
    "server disconnected",
    "try again later",
    "rate limit",
    "too many requests",
    "smtpserverdisconnected",
)
_CONFIGURATION_KEYWORDS = (
    "template",
    "not available in this database",
    "not configured",
    "missing configuration",
    "mail server",
    "module",
    "wizard",
    "contract",
    "group ",
)
_DATA_VALIDATION_KEYWORDS = (
    "missing",
    "required",
    "invalid",
    "duplicate",
    "already exists",
    "must be",
    "checksum",
    "mismatch",
    "not found",
    "unsupported",
)

DEFAULT_OPERATOR_MESSAGES = {
    "retryable_delivery": (
        "A temporary delivery or downstream service failure occurred. Retry after checking the "
        "transport and partner endpoint status."
    ),
    "access_denied": (
        "The request was rejected by the active access policy. Verify credentials, subscriptions, "
        "or portal ownership before retrying."
    ),
    "configuration_error": (
        "A required template, module, or configuration dependency is missing. Correct the "
        "configuration and retry."
    ),
    "data_validation": (
        "The submitted data failed validation. Review the highlighted fields or row errors and retry."
    ),
    "operator_input": (
        "The requested action is not allowed in the current record state. Review the operator "
        "inputs and retry."
    ),
    "unexpected_bug": (
        "An unexpected server error occurred. Retry once, then escalate to engineering if the "
        "problem persists."
    ),
}


def normalize_operator_message(message):
    """Collapse raw text into a single operator-facing line."""
    return re.sub(r"\s+", " ", (message or "").strip())


def is_safe_operator_detail(message):
    """Return whether the text looks safe to persist for operators."""
    normalized = normalize_operator_message(message)
    if not normalized:
        return False
    lowered = normalized.lower()
    if any(marker in lowered for marker in _TRACEBACK_MARKERS):
        return False
    return len(normalized) <= 240


def infer_failure_category(detail=None, error=None, default_category="unexpected_bug"):
    """Infer a stable failure category from an exception or free-form detail."""
    detail = normalize_operator_message(detail or str(error or ""))
    lowered = detail.lower()
    if isinstance(error, AccessError):
        return "access_denied"
    if isinstance(error, ValidationError):
        if any(keyword in lowered for keyword in _CONFIGURATION_KEYWORDS):
            return "configuration_error"
        return "data_validation"
    if isinstance(error, UserError):
        if any(keyword in lowered for keyword in _CONFIGURATION_KEYWORDS):
            return "configuration_error"
        return "operator_input"
    if any(keyword in lowered for keyword in _TRANSIENT_KEYWORDS):
        return "retryable_delivery"
    if any(keyword in lowered for keyword in _CONFIGURATION_KEYWORDS):
        return "configuration_error"
    if any(keyword in lowered for keyword in _DATA_VALIDATION_KEYWORDS):
        return "data_validation"
    return default_category


def build_failure_feedback(error=None, detail=None, default_category="unexpected_bug"):
    """Return a typed failure category and sanitized operator message."""
    detail = normalize_operator_message(detail or str(error or ""))
    category = infer_failure_category(
        detail=detail,
        error=error,
        default_category=default_category,
    )
    if category in (
        "access_denied",
        "configuration_error",
        "data_validation",
        "operator_input",
    ) and is_safe_operator_detail(detail):
        return category, detail
    if category == "retryable_delivery" and is_safe_operator_detail(detail):
        return category, f"{DEFAULT_OPERATOR_MESSAGES[category]} Detail: {detail}"
    return category, DEFAULT_OPERATOR_MESSAGES[category]


def get_failure_category_label(category):
    """Return the human-readable label for a failure category."""
    return FAILURE_CATEGORY_LABELS.get(category, category or "Unknown Failure")
