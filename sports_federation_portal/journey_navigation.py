"""Small pure helpers: route keys, not user-supplied redirect URLs."""
from urllib.parse import urlencode, urlsplit
import re

RETURNS = {
    "club": "/my/action-items",
    "home": "/my/work",
    "official": "/my/referee-assignments",
    "manager": "/federation/operations/action-items",
}
FILTERS = {
    "scope": {"my", "club"},
    "status": {"open", "recent"},
    "task_type": {"registration", "roster_readiness", "parental_consent", "gameday_lineup", "referee_duty", "result_review"},
    "filterby": {"upcoming", "pending", "history", "all"},
}


def return_url(key="club", values=None):
    path = RETURNS.get(key, RETURNS["club"])
    clean = {k: v for k, v in (values or {}).items() if k in FILTERS and v in FILTERS[k]}
    return path + ("?" + urlencode(clean) if clean else "")


def safe_destination(value):
    """Only known record/list routes produced by owning workflows are allowed."""
    if not isinstance(value, str) or any(c in value for c in ("\\", "%", "\r", "\n")):
        return False
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or parts.fragment or parts.query:
        return False
    return bool(re.fullmatch(
        r"/my/(?:competition-entries|rosters|match-sheets|referee-duties|results)(?:/[1-9][0-9]*)?"
        r"|/my/players/[1-9][0-9]*/parental-approvals"
        r"|/my/work/registrations/[1-9][0-9]*", parts.path))


def presentation(state, audience, source_model, source_state, pending_consent=False):
    if state == "done":
        return "completed", "none"
    if source_state is None:
        return "unavailable", "unknown"
    waiting = audience == "club" and (
        (source_model in ("federation.competition.entry", "federation.match.sheet") and source_state == "submitted")
        or pending_consent
    )
    return ("waiting", "federation") if waiting else ("actionable", "club" if audience == "club" else "federation")


def reviewer_can_act(state, user_id, submitted_by_id, verified_by_id,
                     self_verification_allowed=False, self_approval_allowed=False):
    """Mirror the result workflow's actor-separation policy for queue visibility."""
    if state == "submitted":
        return bool(self_verification_allowed or submitted_by_id != user_id)
    if state == "verified":
        return bool(
            self_approval_allowed
            or (submitted_by_id != user_id and verified_by_id != user_id)
        )
    return False
