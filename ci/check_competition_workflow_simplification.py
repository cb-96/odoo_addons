#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []
mapfile = (ROOT / "docs/architecture/competition-model.md").read_text()
for entity in (
    "Competition",
    "Edition",
    "Division",
    "Registration Window",
    "Participant Set",
    "Participant",
    "Structure",
    "Stage",
    "Fixture",
    "Game Day",
    "Slot",
    "Schedule",
    "Publication",
    "Match",
):
    if ("**%s**" % entity) not in mapfile:
        errors.append("entity map lacks " + entity)
service = (
    ROOT / "sports_federation_setup_flow/models/lifecycle_postconditions.py"
).read_text()
for handoff in (
    "registration_finalized",
    "format_frozen",
    "schedule_generated",
    "schedule_published",
    "matchday_opened",
    "matchday_closed",
    "competition_finished",
    "competition_archived",
):
    if "_check_" + handoff not in service:
        errors.append("missing handoff postcondition " + handoff)
nav = (ROOT / "docs/user-guide/backend-navigation.md").read_text()
if (
    "Competition -> Teams -> Format -> Game days -> Schedule -> Publish -> Play -> Finish"
    not in nav
):
    errors.append("ordinary journey not documented")
view = (ROOT / "sports_federation_matchday/views/matchday_views.xml").read_text()
for legacy in ("Operational Schedule Change", "Operational Deviations"):
    if legacy in view:
        errors.append("ordinary match-day UI still exposes " + legacy)
if errors:
    print("Competition workflow simplification failed:\n- " + "\n- ".join(errors))
    sys.exit(1)
print("Competition workflow simplification passed.")
