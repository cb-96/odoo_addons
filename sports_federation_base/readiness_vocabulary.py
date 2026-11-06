"""Federation-wide readiness vocabulary and pure projection helpers.

Every user-facing readiness indicator in the platform speaks one language:

* ``ready``           - everything required is in place
* ``action_needed``   - somebody has to do something, and we know what
* ``waiting_review``  - submitted; another person has to review or approve it
* ``blocked``         - a failed condition prevents progress until resolved
* ``complete``        - the work is finished and closed
* ``not_applicable``  - nothing is required here

Technical models keep their own detailed lifecycle states. This module only
maps those states onto the shared vocabulary, aggregates several statuses into
one answer, and defines the actionable blocker contract (problem, owner,
deadline, action, destination) that every non-ready status has to honour.

The module is plain Python so release tooling and unit tests can import it
without an Odoo runtime. Translation happens in the Odoo layer.
"""

READY = "ready"
ACTION_NEEDED = "action_needed"
WAITING_REVIEW = "waiting_review"
BLOCKED = "blocked"
COMPLETE = "complete"
NOT_APPLICABLE = "not_applicable"

STATUSES = (
    READY,
    ACTION_NEEDED,
    WAITING_REVIEW,
    BLOCKED,
    COMPLETE,
    NOT_APPLICABLE,
)

# Statuses that mean "somebody still has to do something".
ATTENTION = frozenset({BLOCKED, ACTION_NEEDED, WAITING_REVIEW})

LABELS = {
    READY: "Ready",
    ACTION_NEEDED: "Action needed",
    WAITING_REVIEW: "Waiting for review",
    BLOCKED: "Blocked",
    COMPLETE: "Complete",
    NOT_APPLICABLE: "Not applicable",
}

SELECTION = [(code, LABELS[code]) for code in STATUSES]

BADGE_CLASSES = {
    READY: "text-bg-success",
    ACTION_NEEDED: "text-bg-warning",
    WAITING_REVIEW: "text-bg-info",
    BLOCKED: "text-bg-danger",
    COMPLETE: "text-bg-success",
    NOT_APPLICABLE: "text-bg-secondary",
}

# Wording that used to describe readiness on volunteer-facing surfaces. The
# release contract rejects these literals on the surfaces listed in
# ``ci/contracts/readiness_vocabulary.json``.
LEGACY_LABELS = frozenset(
    {
        "Checked",
        "Not checked",
        "Not fully checked",
        "Current checks complete",
        "Needs action",
    }
)

# Detailed internal state -> shared status. Internal states are never renamed;
# they are only translated for display.
STATE_MAPPINGS = {
    # Duty coverage of a match (federation.match.coverage_state).
    "coverage": {
        "unchecked": ACTION_NEEDED,
        "not_required": NOT_APPLICABLE,
        "uncovered": ACTION_NEEDED,
        "needs_action": ACTION_NEEDED,
        "ready": READY,
    },
    # Portal preparation journeys (participation and requirement states).
    "journey": {
        "action": ACTION_NEEDED,
        "waiting": WAITING_REVIEW,
        "unknown": ACTION_NEEDED,
        "complete": COMPLETE,
        "not_applicable": NOT_APPLICABLE,
    },
    # Eligibility evaluator outcomes.
    "eligibility": {
        "pass": READY,
        "fail": BLOCKED,
        "review_required": WAITING_REVIEW,
        "not_applicable": NOT_APPLICABLE,
    },
    # Compliance checks (federation.compliance.check.status).
    "compliance": {
        "compliant": READY,
        "missing": ACTION_NEEDED,
        "pending": WAITING_REVIEW,
        "expired": ACTION_NEEDED,
        "non_compliant": BLOCKED,
    },
    # Game-day line-ups (federation.match.sheet.state).
    "lineup": {
        "not_started": ACTION_NEEDED,
        "draft": ACTION_NEEDED,
        "rejected": ACTION_NEEDED,
        "submitted": WAITING_REVIEW,
        "approved": READY,
        "locked": COMPLETE,
    },
    # Rosters (federation.team.roster.status).
    "roster": {
        "draft": ACTION_NEEDED,
        "active": READY,
        "closed": COMPLETE,
    },
    # Schedules (federation.schedule.state).
    "schedule": {
        "draft": ACTION_NEEDED,
        "ready_for_review": WAITING_REVIEW,
        "changes_requested": ACTION_NEEDED,
        "approved": ACTION_NEEDED,
        "published": READY,
        "superseded": NOT_APPLICABLE,
    },
    # Courts on a game day (federation.matchday.court.status.state).
    "court": {
        "available": READY,
        "delayed": ACTION_NEEDED,
        "unavailable": BLOCKED,
    },
}

# The order in which game-day components are presented.
COMPONENT_ORDER = (
    "schedule",
    "rosters",
    "lineups",
    "officials",
    "courts",
    "eligibility",
    "compliance",
)

OWNER_UNASSIGNED = "unassigned"
OWNER_ASSIGNED = "assigned"


def status_for(domain, state):
    """Map one internal state to the shared vocabulary.

    A state that is not mapped is never reported as ready: "cannot determine"
    must not silently become "fine".
    """
    return STATE_MAPPINGS.get(domain, {}).get(state, ACTION_NEEDED)


def label_for(status):
    """Return the English label of a shared status."""
    return LABELS[status]


def aggregate(statuses):
    """Combine several statuses into the one that answers "is it fine?".

    Blocked beats action needed beats waiting for review. When nothing needs
    attention the result is ``complete`` only if every applicable status is
    complete, ``not_applicable`` if nothing applies and ``ready`` otherwise.
    """
    statuses = list(statuses)
    for status in statuses:
        if status not in STATUSES:
            raise ValueError("Unknown readiness status: %r" % (status,))
    for status in (BLOCKED, ACTION_NEEDED, WAITING_REVIEW):
        if status in statuses:
            return status
    applicable = [status for status in statuses if status != NOT_APPLICABLE]
    if not applicable:
        return NOT_APPLICABLE
    if all(status == COMPLETE for status in applicable):
        return COMPLETE
    return READY


def ratio_status(ready, total, waiting=0, blocked=0):
    """Status of a "7 / 8 ready" style counter.

    ``waiting`` and ``blocked`` count the items that are not ready because they
    wait for review or fail a condition. Items that are neither ready, waiting
    nor blocked need action.
    """
    if total <= 0:
        return NOT_APPLICABLE
    if blocked:
        return BLOCKED
    if ready + waiting < total:
        return ACTION_NEEDED
    if waiting:
        return WAITING_REVIEW
    return READY


def format_ratio(ready, total):
    """Return the compact counter shown next to a component."""
    return "%s / %s ready" % (ready, total)


def make_destination(model, res_id=None, domain=None, view="form", method=None):
    """Return where the person has to go to resolve a blocker."""
    if not model:
        raise ValueError("A blocker destination needs a model.")
    if res_id is None and domain is None:
        raise ValueError("A blocker destination needs a record or a domain.")
    if view not in ("form", "list"):
        raise ValueError("A blocker destination view is 'form' or 'list'.")
    return {
        "model": model,
        "res_id": res_id,
        "domain": [list(term) for term in domain] if domain is not None else None,
        "view": view,
        "method": method,
    }


def make_blocker(
    key,
    status,
    problem,
    action,
    destination,
    owner=None,
    deadline=None,
    count=1,
    details=(),
):
    """Build one actionable blocker.

    Every blocker states the problem, who owns it, by when, what to do and where
    to do it. A missing owner or deadline is kept visible (``owner`` or
    ``deadline`` is ``None``) rather than invented.
    """
    if status not in ATTENTION:
        raise ValueError("A blocker needs an attention status, got %r." % (status,))
    if not (problem or "").strip():
        raise ValueError("A blocker needs a problem statement.")
    if not (action or "").strip():
        raise ValueError("A blocker needs an action.")
    if not isinstance(destination, dict) or not destination.get("model"):
        raise ValueError("A blocker needs a destination.")
    return {
        "key": key,
        "status": status,
        "problem": problem.strip(),
        "owner": (owner or "").strip() or None,
        "owner_state": OWNER_ASSIGNED if (owner or "").strip() else OWNER_UNASSIGNED,
        "deadline": deadline or None,
        "action": action.strip(),
        "destination": destination,
        "count": count,
        "details": list(details),
    }


def make_component(key, status, summary, blockers=(), ready=None, total=None):
    """Build one game-day component.

    A component that is not ready, complete or not applicable must explain
    itself with at least one blocker, so no status is ever a dead end.
    """
    if status not in STATUSES:
        raise ValueError("Unknown readiness status: %r" % (status,))
    blockers = list(blockers)
    if status in ATTENTION and not blockers:
        raise ValueError(
            "Component %r is %s but offers no actionable blocker." % (key, status)
        )
    for blocker in blockers:
        for field in ("problem", "owner", "deadline", "action", "destination"):
            if field not in blocker:
                raise ValueError("Blocker for %r lacks %s." % (key, field))
    return {
        "key": key,
        "status": status,
        "summary": summary,
        "ready": ready,
        "total": total,
        "blockers": blockers,
    }


_SEVERITY = {BLOCKED: 0, ACTION_NEEDED: 1, WAITING_REVIEW: 2}


def blocker_sort_key(blocker):
    """Most severe first, then earliest deadline, then stable by key."""
    deadline = blocker["deadline"] or "9999-12-31"
    return (_SEVERITY[blocker["status"]], deadline, blocker["key"])


def project(components):
    """Aggregate components into the single "can this game day run?" answer."""
    components = list(components)
    keys = [component["key"] for component in components]
    if len(keys) != len(set(keys)):
        raise ValueError("Readiness components must be unique.")

    def order(component):
        key = component["key"]
        if key in COMPONENT_ORDER:
            return (0, COMPONENT_ORDER.index(key))
        return (1, 0)

    components.sort(key=order)
    overall = aggregate(component["status"] for component in components)
    blockers = sorted(
        (blocker for component in components for blocker in component["blockers"]),
        key=blocker_sort_key,
    )
    return {
        "overall": overall,
        "can_run": overall == READY,
        "components": components,
        "blockers": blockers,
    }
