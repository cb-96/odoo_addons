#!/usr/bin/env python3
"""Collect current repository sources required for Packages 3 and 4.

Run from the Odoo addons repository root:
    cp collect_packages_3_4_sources.py.txt collect_packages_3_4_sources.py
    python3 collect_packages_3_4_sources.py

Creates two uploadable text files:
    current_sources.txt
    git_metadata.txt
"""

from pathlib import Path
import subprocess

ROOT = Path.cwd().resolve()
SOURCE_OUT = ROOT / "current_sources.txt"
META_OUT = ROOT / "current_git_metadata.txt"
SEPARATOR = "=" * 100

MODULES = [
    "sports_federation_base",
    "sports_federation_rules",
    "sports_federation_tournament",
    "sports_federation_competition_engine",
    "sports_federation_officiating",
    "sports_federation_result_control",
    "sports_federation_portal",
    "sports_federation_notifications",
]

PATTERNS = (
    "minimum_rest|max_consecutive|match_duration|buffer_minutes|"
    "required_referee|confirmation_deadline|nomination_deadline|"
    "res.config.settings|competition.edition|workspace_state|"
    "result_state|action_submit|action_verify|action_approve|"
    "contest|correction|portal|notification|cron|mail.template|"
    "result.control|action inbox"
)


def run(*args):
    return subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ).stdout


if not (ROOT / "sports_federation_competition_engine").is_dir():
    raise SystemExit("Run this script from the addons repository root.")

existing_modules = [name for name in MODULES if (ROOT / name).is_dir()]
files = set()

# Include every Python, XML, JS, SCSS and Markdown file in the smaller policy and
# result modules. For the larger portal/engine modules, include matching files.
for module in existing_modules:
    module_path = ROOT / module
    for path in module_path.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".py", ".xml", ".js", ".scss", ".md", ".csv"}:
            continue
        relative = path.relative_to(ROOT)
        if module in {
            "sports_federation_rules",
            "sports_federation_result_control",
            "sports_federation_notifications",
        }:
            files.add(relative)
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        import re

        if re.search(PATTERNS, text, flags=re.IGNORECASE):
            files.add(relative)

# Always include manifests, model/service initializers, security, and the main
# Competition Workspace client files required to wire new policy/read models.
mandatory = [
    "sports_federation_base/__manifest__.py",
    "sports_federation_rules/__manifest__.py",
    "sports_federation_tournament/__manifest__.py",
    "sports_federation_competition_engine/__manifest__.py",
    "sports_federation_officiating/__manifest__.py",
    "sports_federation_result_control/__manifest__.py",
    "sports_federation_portal/__manifest__.py",
    "sports_federation_notifications/__manifest__.py",
    "sports_federation_competition_engine/static/src/client_actions/competition_workspace/competition_workspace.js",
    "sports_federation_competition_engine/static/src/client_actions/competition_workspace/competition_workspace.xml",
    "sports_federation_competition_engine/static/src/client_actions/competition_workspace/competition_workspace.scss",
    "sports_federation_competition_engine/static/tests/competition_workspace_ui_tests.js",
]
for name in mandatory:
    path = ROOT / name
    if path.is_file():
        files.add(path.relative_to(ROOT))

# Include module initializers and all current migrations for affected modules.
for module in existing_modules:
    module_path = ROOT / module
    for pattern in ("__init__.py", "models/__init__.py", "services/__init__.py"):
        path = module_path / pattern
        if path.is_file():
            files.add(path.relative_to(ROOT))
    migrations = module_path / "migrations"
    if migrations.is_dir():
        for path in migrations.rglob("*.py"):
            files.add(path.relative_to(ROOT))

with SOURCE_OUT.open("w", encoding="utf-8") as bundle:
    bundle.write("# Packages 3 and 4 current source bundle\n\n")
    for relative in sorted(files, key=str):
        path = ROOT / relative
        bundle.write(SEPARATOR + "\n")
        bundle.write(f"FILE: {relative.as_posix()}\n")
        bundle.write(SEPARATOR + "\n\n")
        content = path.read_text(encoding="utf-8", errors="replace")
        bundle.write(content)
        if not content.endswith("\n"):
            bundle.write("\n")
        bundle.write("\n")

metadata = []
metadata.append("=== CURRENT BRANCH ===\n" + run("git", "branch", "--show-current"))
metadata.append("=== CURRENT COMMIT ===\n" + run("git", "rev-parse", "HEAD"))
metadata.append("=== WORKTREE STATUS ===\n" + run("git", "status", "--short"))
metadata.append("=== MODULE VERSIONS ===\n")
for module in existing_modules:
    manifest = ROOT / module / "__manifest__.py"
    if manifest.is_file():
        version_lines = [
            line.strip()
            for line in manifest.read_text(encoding="utf-8").splitlines()
            if '"version"' in line or "'version'" in line
        ]
        metadata.append(
            f"{module}: {' '.join(version_lines) or '[no version found]'}\n"
        )
metadata.append("\n=== RELEVANT RECENT HISTORY ===\n")
metadata.append(
    run("git", "log", "--oneline", "--decorate", "-20", "--", *existing_modules)
)
metadata.append("\n=== DISCOVERED FILE COUNT ===\n")
metadata.append(f"{len(files)}\n")
META_OUT.write_text("\n".join(metadata), encoding="utf-8")

print(
    f"Created {SOURCE_OUT.name}: {len(files)} files, {SOURCE_OUT.stat().st_size / 1024:.1f} KiB"
)
print(f"Created {META_OUT.name}: {META_OUT.stat().st_size / 1024:.1f} KiB")
