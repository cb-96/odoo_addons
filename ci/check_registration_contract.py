#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []
required = {
    "sports_federation_portal/models/federation_competition_entry.py": [
        "_portal_submit_entry",
        "_portal_open_window_for_division",
    ],
    "sports_federation_public_site/controllers/public_competitions.py": [
        "federation.competition.entry",
        "_portal_submit_entry",
    ],
    "sports_federation_reporting/models/report_season_checklist.py": [
        "federation_competition_entry",
        "federation_registration_window",
    ],
    "sports_federation_portal/migrations/19.0.5.0.0/post-migrate.py": [
        "federation_tournament_registration",
        "DROP TABLE",
    ],
}
for rel, needles in required.items():
    p = ROOT / rel
    if not p.exists():
        errors.append(f"missing {rel}")
        continue
    t = p.read_text()
    for needle in needles:
        if needle not in t:
            errors.append(f"{rel}: missing {needle!r}")
for rel in [
    "sports_federation_portal/models/federation_tournament_registration.py",
    "sports_federation_portal/views/federation_tournament_registration_views.xml",
    "sports_federation_portal/data/ir_sequence.xml",
    "sports_federation_portal/tests/test_tournament_registration.py",
]:
    if (ROOT / rel).exists():
        errors.append(f"obsolete V1 registration artifact remains: {rel}")
for p in ROOT.glob("sports_federation_*/**/*"):
    if (
        p.is_file()
        and "migrations" not in p.parts
        and p.suffix in {".py", ".xml", ".csv"}
        and "federation.tournament.registration" in p.read_text(errors="ignore")
    ):
        errors.append(f"active V1 registration reference: {p.relative_to(ROOT)}")
if errors:
    print("Registration contract failed:\n- " + "\n- ".join(errors))
    sys.exit(1)
print("Registration ownership contract passed.")
