#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CHECKS = {
    "sports_federation_schedule_approval/models/publication_integrity.py": [
        "allow_schedule_review_decision",
        "one_live_matchday",
    ],
    "sports_federation_schedule_approval/services/approval_commands.py": [
        '("matchday_id", "=", schedule.matchday_id.id)',
        "expected_publication_id",
        "FOR UPDATE",
    ],
    "sports_federation_schedule_approval/wizards/publish_schedule_wizard.py": [
        "replacement_required",
        "expected_publication_id",
        "action_publish",
    ],
    "sports_federation_matchday/services/matchday_commands.py": [
        "record_schedule_deviation",
        "open_matchday",
        "close_matchday",
        "published_slot_id",
        "operational_slot_id",
    ],
    "sports_federation_matchday/models/operational_control.py": [
        "readiness_state",
        "federation.matchday.deviation",
        "Operational deviation evidence is immutable",
    ],
    "sports_federation_matchday/views/matchday_views.xml": [
        "Open Match Day",
        "Operational Schedule Change",
        "Operational Deviations",
        "Close Match Day",
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

approval_acl = (
    ROOT / "sports_federation_schedule_approval/security/ir.model.access.csv"
).read_text()
for line in approval_acl.splitlines():
    if line.startswith(
        (
            "access_federation_schedule_review_group_schedule_approver,",
            "access_federation_schedule_review_manager,",
        )
    ):
        if not line.endswith(",1,0,0,0"):
            errors.append(f"review decision ACL must be read-only: {line}")

if errors:
    print("Phases 5.1.1-5.3 contract failed:")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)
print("Phases 5.1.1-5.3 contract passed.")
