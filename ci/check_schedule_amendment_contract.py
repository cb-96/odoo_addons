#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
model = (ROOT / "sports_federation_scheduling/models/schedule.py").read_text()
integrity = (ROOT / "sports_federation_scheduling/models/schedule_integrity.py").read_text()
wizard = (ROOT / "sports_federation_scheduling/wizards/amend_schedule_wizard.py").read_text()
view = (ROOT / "sports_federation_scheduling/views/scheduling_views.xml").read_text()
tests = (ROOT / "sports_federation_scheduling/tests/test_schedule_amendment.py").read_text()
checks = {
    "published-only action": 'self.state != "published"' in model,
    "live operations guard": 'matchday_id.state == "open"' in model + integrity,
    "mandatory reason": 'not (reason or "").strip()' in integrity,
    "replacement links": "supersedes_id" in integrity and "superseded_by_id" in integrity,
    "wizard action": "action_amend" in wizard,
    "planner button": "action_open_amend_schedule" in view,
    "regression tests": "TestScheduleAmendment" in tests,
}
failed = [name for name, passed in checks.items() if not passed]
if failed:
    print("Schedule amendment contract failed: " + ", ".join(failed), file=sys.stderr)
    raise SystemExit(1)
print("Schedule amendment contract passed.")
