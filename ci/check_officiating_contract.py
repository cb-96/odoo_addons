#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []
required = {
    "sports_federation_officiating/models/federation_match_referee.py": [
        "logical_fixture_id",
        "matchday_id",
        "publication_id",
        "_assert_competition_matches",
    ],
    "sports_federation_officiating/models/federation_match_club_referee_duty.py": [
        "logical_fixture_id",
        "matchday_id",
        "_assert_competition_matches",
    ],
    "sports_federation_officiating/wizards/federation_matchday_assign_wizard.py": [
        "current_publication_id",
        "schedule_publication_id",
        "logical_fixture_id",
    ],
    "sports_federation_tournament/migrations/19.0.1.4.0/post-migrate.py": [
        "logical_fixture_id IS NULL",
        "pg_constraint",
    ],
}
for relative, needles in required.items():
    path = ROOT / relative
    if not path.exists():
        errors.append(f"missing {relative}")
        continue
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            errors.append(f"{relative}: missing {needle!r}")
for obsolete in (
    "sports_federation_portal/controllers/portal_workspaces.py",
    "sports_federation_portal/controllers/tournament_operations.py",
    "sports_federation_portal/models/federation_tournament_operations.py",
    "sports_federation_portal/models/tournament_operations_board.py",
    "sports_federation_portal/views/portal_tournament_workspace_templates.xml",
    "sports_federation_portal/views/portal_tournament_operations_templates.xml",
    "sports_federation_portal/static/src/components/tournament_operations",
    "sports_federation_officiating/wizards/federation_round_assign_wizard.py",
):
    if (ROOT / obsolete).exists():
        errors.append(f"obsolete V1 artifact remains: {obsolete}")
if errors:
    print("Officiating contract failed:")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)
print("Officiating and legacy-match contract passed.")
