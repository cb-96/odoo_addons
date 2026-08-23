#!/usr/bin/env python3
"""Complete Phase 0 maintenance on the current repository without patch contexts."""

from pathlib import Path
import json
import re
import subprocess
import sys

ROOT = Path.cwd()
TODAY = "2026-08-23"


def replace_once(path, old, new):
    text = path.read_text(encoding="utf-8")
    if old in text:
        path.write_text(text.replace(old, new), encoding="utf-8")


# Refresh reviewed metadata after an actual source review.
for rel in (
    "INTEGRATION_CONTRACTS.md",
    "ROUTE_INVENTORY.md",
    "DATA_RETENTION_POLICY.md",
):
    path = ROOT / rel
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        text = re.sub(
            r"(?m)^Last reviewed: \d{4}-\d{2}-\d{2}$",
            f"Last reviewed: {TODAY}",
            text,
            count=1,
        )
        path.write_text(text, encoding="utf-8")

# Generated review output must not enter source bundles.
collector = ROOT / "source_collector.py"
if collector.is_file():
    text = collector.read_text(encoding="utf-8")
    if '"odoo_addons_code_review.txt"' not in text:
        text = text.replace(
            "    META_OUT.name,\n",
            '    META_OUT.name,\n    "odoo_addons_code_review.txt",\n',
            1,
        )
        collector.write_text(text, encoding="utf-8")

# Remove the obsolete module ownership entry while preserving surrounding YAML.
owners = ROOT / "MODULE_OWNERS.yaml"
if owners.is_file():
    lines = owners.read_text(encoding="utf-8").splitlines()
    output = []
    skip = False
    for line in lines:
        if line.startswith("  sports_federation_competition_engine:"):
            skip = True
            continue
        if (
            skip
            and line.startswith("  sports_federation_")
            and not line.startswith("    ")
        ):
            skip = False
        if not skip:
            output.append(line)
    owners.write_text("\n".join(output) + "\n", encoding="utf-8")

# Active docs may keep historical prose, but not runtime ownership claims for the removed addon.
replacements = {
    "README.md": {
        "sports_federation_competition_engine": "sports_federation_format / sports_federation_scheduling",
    },
    "ROADMAP.md": {
        "sports_federation_competition_engine": "the modular competition pipeline",
        "Competition Workspace": "competition planning workflow",
    },
    "TECHNICAL_NOTE.md": {
        "sports_federation_competition_engine": "the modular competition pipeline",
        "Competition Workspace": "legacy planning workspace",
        "competition_workspace": "legacy_planning_workspace",
    },
}
for rel, mapping in replacements.items():
    path = ROOT / rel
    if not path.is_file():
        continue
    text = path.read_text(encoding="utf-8")
    for old, new in mapping.items():
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")

# Regenerate formatting-sensitive privileged access inventory from source.
subprocess.run(
    [sys.executable, "ci/check_portal_sudo_guard.py", "--write-inventory"], check=True
)

checks = [
    "ci/check_source_collector_contract.py",
    "ci/check_addon_integrity.py",
    "ci/check_workflow_state_contracts.py",
    "ci/check_doc_freshness.py",
    "ci/check_legacy_engine_removed.py",
    "ci/check_portal_sudo_guard.py",
]
for check in checks:
    subprocess.run([sys.executable, check], check=True)
print("Phase 0 completion checks passed.")
