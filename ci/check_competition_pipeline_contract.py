#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
checks = {
    "sports_federation_scheduling/models/schedule_integrity.py": [
        "assert_mutable",
        "Submitted, approved and published schedules are immutable",
    ],
    "sports_federation_scheduling/services/schedule_validator.py": [
        "venue_blackout",
        "rest_shortfall",
        "participants_unresolved",
    ],
    "sports_federation_schedule_approval/models/publication_integrity.py": [
        "snapshot_digest",
        "current_publication_id",
        "published_slot_id",
    ],
    "sports_federation_schedule_approval/services/approval_commands.py": [
        "submitting planner cannot approve",
        "digest_snapshot",
        "schedule_publication_id",
    ],
    "sports_federation_matchday/models/matchday_session.py": [
        "publication_digest",
        "audit evidence",
    ],
    "sports_federation_matchday/services/matchday_commands.py": [
        "current live published match day",
        "resolve_incident",
        "unfinished_match_ids",
    ],
}
errors = []
for rel, tokens in checks.items():
    p = ROOT / rel
    if not p.is_file():
        errors.append(f"missing {rel}")
        continue
    text = p.read_text(encoding="utf-8")
    errors.extend(f"{rel}: missing {t}" for t in tokens if t not in text)
if errors:
    print("Phases 3-5 contract failed:")
    [print(f"- {e}") for e in errors]
    sys.exit(1)
print("Phases 3-5 contract passed.")
