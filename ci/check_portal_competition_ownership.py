#!/usr/bin/env python3
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
contract = json.loads((ROOT / "ci/contracts/portal_competition_ownership.json").read_text())
required = {
    "competition": "federation.competition.edition",
    "participation": "federation.participant.set",
    "publication": "federation.schedule.publication",
    "live_operations": "federation.matchday.session",
}
errors = []
for key, model in required.items():
    if contract["portal_aggregates"].get(key) != model:
        errors.append(f"ownership mismatch for {key}")
checks = {
    "sports_federation_portal/models/competition_queries.py": [
        "federation.portal.competition.queries",
        "federation.portal.matchday.queries",
        "current_publication_id",
        '("current_publication_id.state", "=", "live")',
    ],
    "sports_federation_portal/controllers/competition_portal.py": [
        "/my/competitions",
        "/my/match-days",
        "/sports/match-days/<int:matchday_id>/operations",
    ],
    "sports_federation_portal/views/competition_templates.xml": [
        "portal_my_competitions",
        "portal_my_matchdays",
        "portal_matchday_operations_page",
    ],
}
for relative, needles in checks.items():
    path = ROOT / relative
    if not path.exists():
        errors.append(f"missing {relative}")
        continue
    text = path.read_text(encoding="utf-8")
    for needle in needles:
        if needle not in text:
            errors.append(f"{relative}: missing {needle!r}")
manifest = (ROOT / "sports_federation_portal/__manifest__.py").read_text()
for removed in (
    "portal_tournament_workspace_templates.xml",
    "portal_tournament_operations_templates.xml",
    "static/src/components/tournament_operations/",
):
    if removed in manifest:
        errors.append(f"legacy portal asset remains active: {removed}")
if errors:
    print("Portal ownership contract failed:")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)
print("Portal ownership contract passed.")
