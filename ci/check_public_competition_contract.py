#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
controller = (
    ROOT / "sports_federation_public_site/controllers/public_competitions_current.py"
).read_text()
queries = (
    ROOT / "sports_federation_public_site/services/public_competition_queries.py"
).read_text()
schedule = (
    ROOT / "sports_federation_public_site/services/public_schedule_queries.py"
).read_text()
manifest = (ROOT / "sports_federation_public_site/__manifest__.py").read_text()
public_templates = (
    ROOT / "sports_federation_public_site/views/website_competition_templates.xml"
).read_text()
portal_templates = (
    ROOT / "sports_federation_portal/views/competition_templates.xml"
).read_text()
legacy_controller = (
    ROOT / "sports_federation_public_site/controllers/public_competitions.py"
).read_text()
checks = {
    "edition publication boundary": '("website_published", "=", True)' in queries,
    "division ownership": "division.edition_id == edition" in queries,
    "live publication boundary": '("current_publication_id.state", "=", "live")'
    in queries + controller,
    "immutable publication match boundary": '("schedule_publication_id", "=", publication.id)'
    in schedule,
    "edition routes": "/competitions/<string:edition_slug>" in controller,
    "single competition hub owner": (
        '@http.route(["/competitions"]' not in legacy_controller
    ),
    "single tournament redirect owner": (
        '["/tournaments", "/tournaments/page/<int:page>"]'
        not in legacy_controller
    ),
    "no legacy competition overview alias": (
        '"/competitions/<model(\'federation.tournament\'):tournament>",'
        not in legacy_controller
    ),
    "gameday route": "/gamedays/<int:matchday_id>" in controller,
    "no implementation generation in public copy": " " not in public_templates,
    "no implementation generation in portal copy": " " not in portal_templates,
    "current dependencies": all(
        module in manifest
        for module in (
            "sports_federation_competition_core",
            "sports_federation_format",
            "sports_federation_calendar",
            "sports_federation_schedule_approval",
            "sports_federation_matchday",
        )
    ),
}
failed = [name for name, passed in checks.items() if not passed]
if failed:
    print(
        "Public competition contract failed: " + ", ".join(failed), file=sys.stderr
    )
    raise SystemExit(1)
print("Public competition contract passed.")
