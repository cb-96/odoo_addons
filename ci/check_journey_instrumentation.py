#!/usr/bin/env python3
"""Keep journey instrumentation anonymous, non-intrusive and retained briefly.

* the event model stores only the allowlisted anonymous fields (privacy);
* instrumentation hooks never change what a route or command returns;
* the portal command wrapper re-raises validation errors after counting them;
* events are read-only for managers and pruned by a retention cron.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_FIELDS = {"journey", "event", "screen", "session_key", "user_id", "occurred_on"}
errors: list[str] = []


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def check_model():
    tree = ast.parse(read("sports_federation_portal/models/journey_event.py"))
    fields_found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FederationJourneyEvent":
            for statement in node.body:
                if (
                    isinstance(statement, ast.Assign)
                    and isinstance(statement.value, ast.Call)
                    and isinstance(statement.value.func, ast.Attribute)
                    and isinstance(statement.value.func.value, ast.Name)
                    and statement.value.func.value.id == "fields"
                ):
                    fields_found.update(
                        t.id for t in statement.targets if isinstance(t, ast.Name)
                    )
    extra = fields_found - ALLOWED_FIELDS
    if extra:
        errors.append(
            "federation.journey.event may not store %s (anonymous events only)."
            % sorted(extra)
        )
    missing = ALLOWED_FIELDS - fields_found
    if missing:
        errors.append("federation.journey.event lacks %s." % sorted(missing))
    text = read("sports_federation_portal/models/journey_event.py")
    for needle in ("def record(", "def report(", "def _cron_prune(", "savepoint()"):
        if needle not in text:
            errors.append("journey_event.py lacks %s." % needle)


def check_wrapper():
    text = read("sports_federation_portal/models/portal_privilege_instrumentation.py")
    if "except ValidationError:" not in text or "\n            raise\n" not in text:
        errors.append("The portal command wrapper must re-raise validation errors.")
    if "super().portal_call(" not in text:
        errors.append(
            "The portal command wrapper must delegate to the privilege boundary."
        )
    for forbidden in (".write(", ".create(", ".unlink("):
        if forbidden in text:
            errors.append(
                "The portal command wrapper may not %s records." % forbidden.strip("(.")
            )


def check_controllers():
    text = read("sports_federation_portal/controllers/journey_instrumentation.py")
    tree = ast.parse(text)
    for function in ast.walk(tree):
        if isinstance(function, ast.FunctionDef) and function.name in (
            "role_home",
            "open_task",
            "club_preparation",
        ):
            body = ast.unparse(function)
            if "response = super()" not in body or not body.rstrip().endswith(
                "return response"
            ):
                errors.append(
                    "%s must return the unchanged parent response." % function.name
                )
    if "except Exception" not in text:
        errors.append("Recording an entry must never raise into the route.")


def check_security_and_retention():
    csv = read("sports_federation_portal/security/ir.model.access.csv")
    rows = [
        line for line in csv.splitlines() if "model_federation_journey_event" in line
    ]
    if len(rows) != 1 or not rows[0].endswith(",1,0,0,0"):
        errors.append("Journey events must be read-only for exactly one group.")
    if "group_federation_manager" not in (rows[0] if rows else ""):
        errors.append("Only federation managers may read journey events.")
    if "_cron_prune" not in read(
        "sports_federation_portal/data/journey_event_cron.xml"
    ):
        errors.append("The journey event retention cron is missing.")
    manifest = read("sports_federation_portal/__manifest__.py")
    for entry in ("data/journey_event_cron.xml", "views/journey_event_views.xml"):
        if entry not in manifest:
            errors.append("%s is not in the portal manifest." % entry)


def main() -> int:
    check_model()
    check_wrapper()
    check_controllers()
    check_security_and_retention()
    if errors:
        print("Journey instrumentation contract failed:")
        for error in errors:
            print("- %s" % error)
        return 1
    print("Journey instrumentation contract passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
