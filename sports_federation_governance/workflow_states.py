OVERRIDE_REQUEST_STATE_DRAFT = "draft"
OVERRIDE_REQUEST_STATE_SUBMITTED = "submitted"
OVERRIDE_REQUEST_STATE_APPROVED = "approved"
OVERRIDE_REQUEST_STATE_REJECTED = "rejected"
OVERRIDE_REQUEST_STATE_IMPLEMENTED = "implemented"
OVERRIDE_REQUEST_STATE_CLOSED = "closed"

OVERRIDE_REQUEST_STATE_SELECTION = [
    (OVERRIDE_REQUEST_STATE_DRAFT, "Draft"),
    (OVERRIDE_REQUEST_STATE_SUBMITTED, "Submitted"),
    (OVERRIDE_REQUEST_STATE_APPROVED, "Approved"),
    (OVERRIDE_REQUEST_STATE_REJECTED, "Rejected"),
    (OVERRIDE_REQUEST_STATE_IMPLEMENTED, "Implemented"),
    (OVERRIDE_REQUEST_STATE_CLOSED, "Closed"),
]

OVERRIDE_DECISION_SELECTION = [
    (OVERRIDE_REQUEST_STATE_APPROVED, "Approved"),
    (OVERRIDE_REQUEST_STATE_REJECTED, "Rejected"),
]

OVERRIDE_REQUEST_CLOSABLE_STATES = (
    OVERRIDE_REQUEST_STATE_IMPLEMENTED,
    OVERRIDE_REQUEST_STATE_REJECTED,
)


def is_override_request_submitted(state):
    """Return whether the request is awaiting a governance decision."""
    return state == OVERRIDE_REQUEST_STATE_SUBMITTED


def is_override_request_approved(state):
    """Return whether the request is approved for implementation."""
    return state == OVERRIDE_REQUEST_STATE_APPROVED
