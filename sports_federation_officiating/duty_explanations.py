"""Suggested fixes for blocking club-duty allocation issues.

Each issue detail from ``duty_allocation.allocate`` or the review gets a list of
suggestion codes. The codes are pure data, so previews stay JSON-stable; the
review translates them into operator text.
"""


def _reasons(detail):
    return [str(reason) for reason in (detail.get("rejected") or {}).values()]


def _pinned_reason(detail):
    rejected = detail.get("rejected") or {}
    club = detail.get("club")
    return str(rejected.get(club) or rejected.get(str(club)) or "")


def _capacity_codes(reasons):
    codes = []
    if any("simultaneous capacity" in reason for reason in reasons):
        codes += ["raise_capacity", "shorten_buffers"]
    if any("missing qualifications" in reason for reason in reasons):
        codes.append("qualify_roles")
    return codes


def suggestions(detail, policy=None):
    """Return the ordered, de-duplicated suggestion codes for one issue."""
    policy = policy or {}
    code = detail.get("code")
    codes = []
    if code == "participants_unresolved":
        codes.append("resolve_participants")
    elif code == "pin_conflict":
        codes.append("change_pin")
        codes += _capacity_codes([_pinned_reason(detail)])
    elif code == "capacity_conflict":
        codes += _capacity_codes(_reasons(detail))
        if policy.get("avoid", True) and not policy.get("fallback", False):
            codes.append("allow_fallback")
        codes += ["move_fixture", "assign_referee"]
    elif code == "preserved_conflict":
        codes.append("resolve_existing")
    unique = []
    for item in codes:
        if item not in unique:
            unique.append(item)
    return unique


def attach_suggestions(proposal, policy=None):
    """Add a ``suggestions`` list to every issue detail of ``proposal``."""
    for detail in proposal.get("issue_details") or []:
        detail["suggestions"] = suggestions(detail, policy)
    return proposal


SUGGESTION_CODES = (
    "resolve_participants",
    "change_pin",
    "raise_capacity",
    "shorten_buffers",
    "qualify_roles",
    "allow_fallback",
    "move_fixture",
    "assign_referee",
    "resolve_existing",
)
