"""Policy for actionable work projections.

Operation tasks represent actions, never status. Detailed domain state remains
on its owning record; the work projection only says who acts, what they must do,
by when and where.
"""
CLUB = "club"
MANAGER = "manager"
TASK_TYPES = {
    "registration": ("Competition entry", {CLUB, MANAGER}),
    "roster_readiness": ("Complete roster", {CLUB}),
    "parental_consent": ("Provide parental consent", {CLUB}),
    "consent_verification": ("Verify parental consent", {MANAGER}),
    "gameday_lineup": ("Prepare game-day line-up", {CLUB}),
    "lineup_review": ("Review game-day line-up", {MANAGER}),
    "referee_duty": ("Nominate club official", {CLUB}),
    "result_review": ("Review result", {MANAGER}),
}
TASK_TYPE_SELECTION = [(key, value[0]) for key, value in TASK_TYPES.items()]
STATUS_ONLY = {
    "competition_published", "roster_current", "lineup_approved",
    "no_gamedays", "season_completed",
}
REQUIRED_FIELDS = (
    "name", "task_type", "audience", "blocking_reason", "next_step",
    "source_model", "source_record_id", "source_key",
)

def validate_spec(spec):
    errors = ["missing %s" % name for name in REQUIRED_FIELDS if not spec.get(name)]
    policy = TASK_TYPES.get(spec.get("task_type"))
    if not policy:
        errors.append("unknown task type")
    elif spec.get("audience") not in policy[1]:
        errors.append("wrong task audience")
    return errors

def lineup_task(state):
    return {
        "draft": ("gameday_lineup", CLUB),
        "submitted": ("lineup_review", MANAGER),
    }.get(state)

def consent_task(pending_review):
    return ("consent_verification", MANAGER) if pending_review else ("parental_consent", CLUB)
