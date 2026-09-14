#!/usr/bin/env python3
"""Inventory optional product addons without changing installed databases."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPTIONAL = {
    "sports_federation_compliance": "legal or assurance requirement",
    "sports_federation_discipline": "disciplinary case management",
    "sports_federation_finance_bridge": "finance automation",
    "sports_federation_governance": "governance overrides",
    "sports_federation_import_tools": "managed imports and integrations",
    "sports_federation_notifications": "scheduled notifications",
    "sports_federation_reporting": "advanced reporting and automation",
}


def manifest(module):
    path = ROOT / module / "__manifest__.py"
    return ast.literal_eval(path.read_text()) if path.exists() else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    records = []
    for module, purpose in OPTIONAL.items():
        values = manifest(module)
        records.append(
            {
                "module": module,
                "present": values is not None,
                "installable": bool(values and values.get("installable")),
                "purpose": purpose,
                "decision": "review",
            }
        )
    payload = {"optional_addons": records}
    output = json.dumps(payload, indent=2) + "\n"
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(output)
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
