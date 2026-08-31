#!/usr/bin/env python3
"""Fail fast when the P0-P3 release-focus qualification becomes disconnected."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "sports_federation_demo/static/tests/tours/full_competition_lifecycle_tour.js",
    "sports_federation_demo/tests/test_browser_competition_lifecycle.py",
    "sports_federation_finance_bridge/static/tests/tours/finance_bridge_browser_tour.js",
    "sports_federation_finance_bridge/tests/test_browser_finance_bridge.py",
    "sports_federation_public_site/static/tests/tours/public_site_browser_tour.js",
    "sports_federation_public_site/tests/test_browser_public_site.py",
    "sports_federation_scheduling/tests/test_schedule_amendment.py",
    "sports_federation_schedule_approval/tests/test_review_permissions.py",
    "sports_federation_officiating/tests/test_club_referee_duty.py",
    "sports_federation_officiating/tests/test_competition_officiating_contract.py",
    "sports_federation_governance/tests/test_governance.py",
    "sports_federation_portal/tests/test_production_security_matrix.py",
    "sports_federation_compliance/tests/test_compliance.py",
    "sports_federation_demo/tests/test_release_pilot_readiness.py",
    "docs/RELEASE_PILOT_SCENARIO.md",
)

REQUIRED_SNIPPETS = {
    "sports_federation_demo/tests/__init__.py": ("test_release_pilot_readiness",),
    "sports_federation_demo/__manifest__.py": (
        "full_competition_lifecycle_tour.js",
        '"web_tour"',
    ),
    "sports_federation_finance_bridge/__manifest__.py": (
        "finance_bridge_browser_tour.js",
        '"web_tour"',
    ),
    "sports_federation_public_site/__manifest__.py": (
        "public_site_browser_tour.js",
        '"web_tour"',
    ),
    "scripts/ci/run_rc_validation.sh": (
        "check_release_focus_contract.py",
        "sf_release_focus",
    ),
}

errors: list[str] = []
for relative in REQUIRED_FILES:
    if not (ROOT / relative).is_file():
        errors.append(f"missing release-focus file: {relative}")

for relative, snippets in REQUIRED_SNIPPETS.items():
    path = ROOT / relative
    if not path.is_file():
        errors.append(f"missing contract source: {relative}")
        continue
    source = path.read_text(encoding="utf-8")
    for snippet in snippets:
        if snippet not in source:
            errors.append(f"{relative}: missing {snippet!r}")

if errors:
    print("Release-focus contract failed:", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    raise SystemExit(1)

print("Release-focus contract passed.")
