"""Journey instrumentation: how volunteers actually get through the portal.

Measures, without storing any personal data or record content:

* entry into a workflow (a journey page or a task was opened);
* actions taken (a portal command succeeded) and validation errors (it failed);
* retries (the same command attempted again shortly after a validation error);
* abandonment (a workflow was entered but nothing was done and the user left);
* the average number of screens and actions per session.

Completion of work is *not* guessed from page views: it is read from the
operation tasks themselves (see ``federation.journey.event.report``).

Plain Python so it can be unit tested without an Odoo runtime.
"""

from datetime import timedelta
import hashlib

EVENTS = ("entry", "action", "validation_error", "retry")
_COUNTER = {
    "entry": "entries",
    "action": "actions",
    "validation_error": "validation_errors",
    "retry": "retries",
}
RETRY_WINDOW = timedelta(minutes=10)
DEFAULT_GRACE_MINUTES = 30


def session_key(raw):
    """Hash a session identifier; the raw value is never stored."""
    return hashlib.sha256(("journey:%s" % raw).encode()).hexdigest()[:16]


def _mean(values):
    values = list(values)
    return (sum(values) / len(values)) if values else None


def summarize(events, now, grace_minutes=DEFAULT_GRACE_MINUTES):
    """Summarise ``events`` (dicts with journey, event, session_key, screen, occurred_on)."""
    by_journey, sessions = {}, {}
    for event in events:
        kind = event["event"]
        if kind not in _COUNTER:
            continue
        journey = by_journey.setdefault(
            event["journey"],
            {"entries": 0, "actions": 0, "validation_errors": 0, "retries": 0},
        )
        journey[_COUNTER[kind]] += 1
        key = event.get("session_key")
        if not key:
            continue
        session = sessions.setdefault(
            key,
            {
                "entered": False,
                "actions": 0,
                "screens": set(),
                "last": event["occurred_on"],
            },
        )
        if kind == "entry":
            session["entered"] = True
            if event.get("screen"):
                session["screens"].add(event["screen"])
        elif kind == "action":
            session["actions"] += 1
        if event["occurred_on"] > session["last"]:
            session["last"] = event["occurred_on"]
    for journey in by_journey.values():
        attempts = journey["actions"] + journey["validation_errors"]
        journey["validation_error_rate"] = (
            journey["validation_errors"] / attempts if attempts else None
        )
    grace = timedelta(minutes=grace_minutes)
    entered = [s for s in sessions.values() if s["entered"]]
    worked = [s for s in sessions.values() if s["actions"]]
    idle = [s for s in entered if not s["actions"]]
    abandoned = [s for s in idle if now - s["last"] > grace]
    return {
        "by_journey": by_journey,
        "sessions": {
            "entered": len(entered),
            "worked": len(worked),
            "abandoned": len(abandoned),
            "in_progress": len(idle) - len(abandoned),
            "abandonment_rate": (len(abandoned) / len(entered)) if entered else None,
            "avg_screens": _mean(len(s["screens"]) for s in entered),
            "avg_actions": _mean(s["actions"] for s in worked),
        },
    }
