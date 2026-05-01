# Tournament workflow state constants
# Use these instead of inline string literals so that a state rename is a
# single-file change and typos are caught by import errors.

TOURNAMENT_STATE_DRAFT = "draft"
TOURNAMENT_STATE_OPEN = "open"
TOURNAMENT_STATE_IN_PROGRESS = "in_progress"
TOURNAMENT_STATE_CLOSED = "closed"
TOURNAMENT_STATE_CANCELLED = "cancelled"

TOURNAMENT_STATES_ACTIVE = (TOURNAMENT_STATE_OPEN, TOURNAMENT_STATE_IN_PROGRESS)

TOURNAMENT_STATE_SELECTION = [
    (TOURNAMENT_STATE_DRAFT, "Draft"),
    (TOURNAMENT_STATE_OPEN, "Open"),
    (TOURNAMENT_STATE_IN_PROGRESS, "In Progress"),
    (TOURNAMENT_STATE_CLOSED, "Closed"),
    (TOURNAMENT_STATE_CANCELLED, "Cancelled"),
]

# Match workflow state constants
MATCH_STATE_DRAFT = "draft"
MATCH_STATE_SCHEDULED = "scheduled"
MATCH_STATE_IN_PROGRESS = "in_progress"
MATCH_STATE_DONE = "done"
MATCH_STATE_CANCELLED = "cancelled"

MATCH_STATE_SELECTION = [
    (MATCH_STATE_DRAFT, "Draft"),
    (MATCH_STATE_SCHEDULED, "Scheduled"),
    (MATCH_STATE_IN_PROGRESS, "In Progress"),
    (MATCH_STATE_DONE, "Done"),
    (MATCH_STATE_CANCELLED, "Cancelled"),
]
