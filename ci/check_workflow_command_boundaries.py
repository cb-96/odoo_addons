#!/usr/bin/env python3
"""Keep protected workflow changes behind their owning command services."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCHEDULE = ROOT / "sports_federation_scheduling/services/schedule_commands.py"


def violations(root=ROOT):
    source = (root / SCHEDULE.relative_to(ROOT)).read_text(encoding="utf-8")
    failures = []
    if 'schedule.state = "ready_for_review"' in source:
        failures.append("schedule submission writes protected state directly")
    if 'self.env["federation.workflow.transition"].execute(' not in source:
        failures.append("schedule submission does not use the transition service")
    if 'event_type="schedule_submitted"' not in source:
        failures.append("schedule submission has no workflow audit event")
    return failures


def main():
    failures = violations()
    if failures:
        print("Workflow command boundary check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Workflow command boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
