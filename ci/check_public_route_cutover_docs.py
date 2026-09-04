#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
contracts = (ROOT / "INTEGRATION_CONTRACTS.md").read_text(encoding="utf-8")
inventory = (ROOT / "ROUTE_INVENTORY.md").read_text(encoding="utf-8")
readme = (ROOT / "sports_federation_public_site/README.md").read_text(encoding="utf-8")
forbidden = ("/" + "tournaments", "/" + "tournament/", "/api/v1/" + "tournaments")
failures = []
for name, content in (
    ("integration contracts", contracts),
    ("route inventory", inventory),
    ("public-site README", readme),
):
    for token in forbidden:
        if token in content:
            failures.append(f"{name} still documents removed route {token}")
for token in ("/api/v1/competitions", "/competitions/<edition-slug>"):
    if token not in contracts + inventory + readme:
        failures.append(f"canonical competition route is undocumented: {token}")
if failures:
    print(
        "Public route namespace documentation failed: " + "; ".join(failures),
        file=sys.stderr,
    )
    raise SystemExit(1)
print("Public route namespace documentation passed.")
