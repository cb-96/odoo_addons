#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
checks = {
    "ADR canonical namespace": "/competitions" in (ROOT / "adr/0003-public-route-ownership.md").read_text(),
    "route inventory canonical namespace": "under `/competitions`" in (ROOT / "ROUTE_INVENTORY.md").read_text(),
    "public workflow canonical edition route": "/competitions/<edition-slug>" in (ROOT / "_workflows/WORKFLOW_PUBLIC_PUBLICATION.md").read_text(),
    "integration deprecates tournament pages": "`/tournaments`, `/tournaments/<slug>`" in (ROOT / "INTEGRATION_CONTRACTS.md").read_text(),
}
failed = [name for name, passed in checks.items() if not passed]
if failed:
    print("Public route cutover documentation failed: " + ", ".join(failed), file=sys.stderr)
    raise SystemExit(1)
print("Public route cutover documentation passed.")
