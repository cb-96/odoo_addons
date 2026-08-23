#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

CHECKS = {
    "sports_federation_scheduling/models/schedule.py": [
        "action_open_submit_for_review",
        "action_submit_for_review",
        'self.env["federation.schedule.commands"].submit',
    ],
    "sports_federation_scheduling/views/scheduling_views.xml": [
        "action_open_submit_for_review",
        "Submit for Review",
    ],
    "sports_federation_schedule_approval/models/workflow_actions.py": [
        "action_open_current_review",
        "action_request_changes",
        "action_approve_schedule",
        "action_publish_schedule",
        'self.env["federation.schedule.approval.commands"]',
    ],
    "sports_federation_schedule_approval/services/approval_commands.py": [
        "start_review",
        "request_changes",
        "approve",
        "publish",
        "The submitting planner cannot approve their own schedule",
    ],
    "sports_federation_schedule_approval/views/approval_views.xml": [
        "Schedule Review Queue",
        "Approved Schedules",
        "Schedule Publications",
        "Request Changes",
        "Approve Schedule",
        "Publish Schedule",
    ],
}

errors = []
for relative, needles in CHECKS.items():
    path = ROOT / relative
    if not path.exists():
        errors.append(f"missing {relative}")
        continue
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            errors.append(f"{relative}: missing {needle!r}")

approval_xml = (ROOT / "sports_federation_schedule_approval/views/approval_views.xml").read_text(encoding="utf-8")
for direct_service in ("approval.commands.approve", "approval.commands.publish"):
    if direct_service in approval_xml:
        errors.append(f"approval view bypasses model command wrapper: {direct_service}")

if errors:
    print("Phase 5.1 schedule handoff contract failed:")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)
print("Phase 5.1 schedule handoff contract passed.")
