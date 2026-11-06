("Pure coverage projection: an assignment is never proof " "of readiness.")


def project(requirements, assignments, pending_duties=0, checked=True):
    active = [a for a in assignments if a["active"]]
    assigned = len(active)
    accepted = sum(bool(a["accepted"]) for a in active)
    eligible = sum(bool(a["eligible"]) for a in active)
    present = sum(bool(a["present"]) for a in active)
    completed = sum(bool(a["completed"]) for a in active)
    missing = {}
    ready_missing = {}
    for role, required in requirements.items():
        rows = [a for a in active if a["role"] == role]
        missing[role] = max(0, required - len(rows))
        ready_missing[role] = max(
            0, required - sum(a["accepted"] and a["eligible"] for a in rows)
        )
    required = sum(requirements.values())
    if not checked:
        state = "unchecked"
    elif not required and not pending_duties:
        state = "not_required"
    elif sum(missing.values()):
        state = "uncovered"
    elif pending_duties or sum(ready_missing.values()):
        state = "needs_action"
    else:
        state = "ready"
    return dict(
        state=state,
        required=required,
        assigned=assigned,
        accepted=accepted,
        eligible=eligible,
        present=present,
        completed=completed,
        missing=missing,
        ready_missing=ready_missing,
    )
