#!/usr/bin/env python3
"""Collect the complete Sports Federation source state for review and patching.

Run from the Git repository root containing the Odoo addons:

    python3 source_collector.py

Creates:

    current_sources.txt
    current_git_metadata.txt

The collector deliberately avoids keyword-based filtering. Every relevant text
source file from the configured addons and repository engineering directories is
included. Manifest data and explicit asset references are validated before the
output files are replaced.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Iterable


ROOT = Path.cwd().resolve()
SOURCE_OUT = ROOT / "current_sources.txt"
META_OUT = ROOT / "current_git_metadata.txt"
SEPARATOR = "=" * 100
MAX_TEXT_FILE_SIZE = 10 * 1024 * 1024

# Addons are discovered dynamically. A manual allowlist caused internal dependency
# addons to disappear from review bundles and made "full codebase" reviews partial.
MODULES: list[str] = []

TEXT_EXTENSIONS = {
    ".bash",
    ".cfg",
    ".conf",
    ".csv",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".po",
    ".pot",
    ".py",
    ".rst",
    ".scss",
    ".sh",
    ".sql",
    ".svg",
    ".toml",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}

TEXT_FILENAMES = {
    ".gitignore",
    ".pre-commit-config.yaml",
    ".pylintrc",
    "Dockerfile",
    "LICENSE",
    "Makefile",
    "README",
}

EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    ".vscode",
    "__pycache__",
    "coverage",
    "dist",
    "htmlcov",
    "node_modules",
    "venv",
}

EXCLUDED_FILENAMES = {
    SOURCE_OUT.name,
    META_OUT.name,
    "odoo_addons_code_review.txt",
}

EXCLUDED_PATH_PREFIXES = {
    Path("ci/logs"),
    Path("_logs"),
}

# This legacy manifest entry is intentionally retained for compatibility, but
# the stylesheet was removed from the current source tree and must not make
# source collection fail.
NON_REQUIRED_EXPLICIT_ASSETS = {
    Path(
        "sports_federation_public_site/static/src/scss/"
        "public_competitions_current.scss"
    ),
}

REPOSITORY_FILES = [
    "source_collector.py",
    ".gitignore",
    ".pre-commit-config.yaml",
    "CHANGELOG.md",
    "CONTEXT.md",
    "CONTRIBUTING.md",
    "DEPLOYMENT_GUIDE.md",
    "DOCUMENTATION_REVIEW.md",
    "Dockerfile",
    "LICENSE",
    "Makefile",
    "MODULE_OWNERS.yaml",
    "README.md",
    "RELEASE_RUNBOOK.md",
    "ROADMAP.md",
    "ROUTE_INVENTORY.md",
    "SECURITY.md",
    "STATE_AND_OWNERSHIP_MATRIX.md",
    "TECHNICAL_NOTE.md",
    "TESTING_GUIDE.md",
    "docker-compose.yml",
    "pyproject.toml",
    "requirements-dev.txt",
    "requirements.txt",
    "ruff.toml",
]

REPOSITORY_DIRECTORIES = [
    ".github",
    "_workflows",
    "ci",
    "docs",
    "scripts",
    "adr",
]


def run(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if check and process.returncode:
        raise SystemExit(
            f"Command failed with exit code {process.returncode}: {' '.join(args)}\n"
            f"{process.stdout}"
        )
    return process


def command_output(*args: str, check: bool = False) -> str:
    return run(*args, check=check).stdout.rstrip()


def validate_repository_root() -> None:
    top_level = command_output("git", "rev-parse", "--show-toplevel", check=True)
    if top_level != str(ROOT):
        raise SystemExit("Run this script from the Git repository root.")

    required = [
        ROOT / "sports_federation_base",
        ROOT / "sports_federation_competition_core",
    ]
    missing = [path.name for path in required if not path.is_dir()]
    if missing:
        raise SystemExit(
            "Repository validation failed. Missing required addon directories: "
            + ", ".join(missing)
        )


def is_excluded(path: Path) -> bool:
    if path.name in EXCLUDED_FILENAMES:
        return True
    # Patch exports are archival review artifacts, not current repository source.
    # Keeping them out prevents removed implementation names from being copied
    # back into the generated source bundle.
    if path.name.endswith(".patch.txt"):
        return True
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return True
    if any(relative == prefix or prefix in relative.parents for prefix in EXCLUDED_PATH_PREFIXES):
        return True
    return any(part in EXCLUDED_DIRECTORY_NAMES for part in relative.parts)


def is_supported_text_file(path: Path) -> bool:
    if not path.is_file() or is_excluded(path):
        return False
    return path.name in TEXT_FILENAMES or path.suffix.lower() in TEXT_EXTENSIONS


def repository_relative(path: Path) -> Path:
    try:
        return path.resolve().relative_to(ROOT)
    except ValueError as exc:
        raise SystemExit(f"Refusing to collect path outside repository: {path}") from exc


def collect_directory(directory: Path) -> set[Path]:
    files: set[Path] = set()
    if not directory.is_dir():
        return files
    for path in directory.rglob("*"):
        if is_supported_text_file(path):
            files.add(repository_relative(path))
    return files


def discover_addons() -> list[str]:
    """Return every repository addon containing a parseable Odoo manifest."""
    addons = []
    for manifest in ROOT.glob("*/__manifest__.py"):
        addon = manifest.parent
        if is_excluded(addon):
            continue
        addons.append(addon.name)
    return sorted(set(addons))


def collect_repository_root_files() -> set[Path]:
    """Collect supported root-level files without maintaining another allowlist."""
    return {
        repository_relative(path)
        for path in ROOT.iterdir()
        if is_supported_text_file(path)
    }


def validate_internal_dependencies(existing_modules: list[str]) -> None:
    """Fail when a collected federation addon depends on an uncollected peer."""
    available = set(existing_modules)
    missing: list[str] = []
    for module in existing_modules:
        manifest = parse_manifest(module)
        for dependency in manifest.get("depends", []):
            if isinstance(dependency, str) and dependency.startswith("sports_federation_"):
                if dependency not in available:
                    missing.append(f"{module}: unresolved internal dependency {dependency}")
    if missing:
        raise SystemExit(
            "Internal addon dependency validation failed:\n"
            + "\n".join(f"  - {item}" for item in sorted(set(missing)))
        )


def collect_files(existing_modules: Iterable[str]) -> list[Path]:
    files: set[Path] = set()
    for module in existing_modules:
        files.update(collect_directory(ROOT / module))
    files.update(collect_repository_root_files())
    for filename in REPOSITORY_FILES:
        path = ROOT / filename
        if is_supported_text_file(path):
            files.add(repository_relative(path))
    for directory in REPOSITORY_DIRECTORIES:
        files.update(collect_directory(ROOT / directory))
    return sorted(files, key=lambda path: path.as_posix())


def read_text(path: Path) -> str:
    size = path.stat().st_size
    if size > MAX_TEXT_FILE_SIZE:
        raise SystemExit(
            f"Refusing to bundle text file larger than {MAX_TEXT_FILE_SIZE} bytes: "
            f"{path.relative_to(ROOT)}"
        )
    return path.read_text(encoding="utf-8", errors="replace")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_manifest(module: str) -> dict:
    manifest_path = ROOT / module / "__manifest__.py"
    if not manifest_path.is_file():
        raise SystemExit(f"Missing manifest: {manifest_path.relative_to(ROOT)}")
    try:
        manifest = ast.literal_eval(manifest_path.read_text(encoding="utf-8"))
    except (SyntaxError, ValueError, UnicodeError) as exc:
        raise SystemExit(
            f"Cannot parse {manifest_path.relative_to(ROOT)}: {exc}"
        ) from exc
    if not isinstance(manifest, dict):
        raise SystemExit(
            f"Manifest is not a dictionary: {manifest_path.relative_to(ROOT)}"
        )
    return manifest


def explicit_asset_path(module: str, value: str) -> Path | None:
    if not value or any(character in value for character in "*?["):
        return None
    prefix = module + "/"
    if not value.startswith(prefix):
        return None
    return Path(module) / value[len(prefix) :]


def validate_manifest_references(
    existing_modules: list[str], bundled_files: set[Path]
) -> list[dict]:
    errors: list[str] = []
    summaries: list[dict] = []

    for module in existing_modules:
        manifest = parse_manifest(module)
        module_root = ROOT / module
        data_entries: list[str] = []
        explicit_assets: list[str] = []

        for value in manifest.get("data", []):
            if not isinstance(value, str):
                errors.append(f"{module}: non-string manifest data entry: {value!r}")
                continue
            data_entries.append(value)
            path = module_root / value
            relative = Path(module) / value
            if not path.is_file():
                errors.append(f"{module}: missing manifest data file: {value}")
            elif is_supported_text_file(path) and relative not in bundled_files:
                errors.append(f"{module}: manifest data file omitted from bundle: {value}")

        for bundle_name, entries in manifest.get("assets", {}).items():
            if not isinstance(entries, (list, tuple)):
                errors.append(
                    f"{module}: asset bundle {bundle_name!r} is not a list or tuple"
                )
                continue
            for entry in entries:
                if not isinstance(entry, str):
                    continue
                relative = explicit_asset_path(module, entry)
                if relative is None:
                    continue
                explicit_assets.append(entry)
                if relative in NON_REQUIRED_EXPLICIT_ASSETS:
                    continue
                path = ROOT / relative
                if not path.is_file():
                    errors.append(f"{module}: missing explicit asset file: {entry}")
                elif is_supported_text_file(path) and relative not in bundled_files:
                    errors.append(f"{module}: explicit asset omitted from bundle: {entry}")

        summaries.append(
            {
                "module": module,
                "name": manifest.get("name"),
                "version": manifest.get("version"),
                "depends": manifest.get("depends", []),
                "data": data_entries,
                "explicit_assets": explicit_assets,
                "installable": manifest.get("installable", True),
                "application": manifest.get("application", False),
                "auto_install": manifest.get("auto_install", False),
            }
        )

    if errors:
        raise SystemExit(
            "Manifest/source validation failed. Output files were not replaced:\n"
            + "\n".join(f"  - {error}" for error in errors)
        )
    return summaries


def validate_collection_contract(files: list[Path]) -> None:
    bundled = set(files)
    required = {
        Path("source_collector.py"),
        Path("ci/run_tests.sh"),
        Path("ci/run_odoo_tests.sh"),
        Path("scripts/ci/run_rc_validation.sh"),
    }
    existing_required = {path for path in required if (ROOT / path).is_file()}
    missing = existing_required - bundled
    if missing:
        raise SystemExit(
            "Collector omitted required repository files:\n"
            + "\n".join(f"  - {path.as_posix()}" for path in sorted(missing))
        )


def nul_git_paths(*args: str) -> set[str]:
    process = subprocess.run(
        ("git", *args),
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.returncode:
        return set()
    return {
        item.decode("utf-8", errors="replace")
        for item in process.stdout.split(b"\0")
        if item
    }


def git_state_sets() -> tuple[set[str], set[str], set[str]]:
    tracked = nul_git_paths("ls-files", "-z")
    modified = nul_git_paths("diff", "--name-only", "-z")
    modified.update(nul_git_paths("diff", "--cached", "--name-only", "-z"))
    untracked = nul_git_paths("ls-files", "--others", "--exclude-standard", "-z")
    return tracked, modified, untracked


def classify_git_state(
    relative: Path,
    tracked: set[str],
    modified: set[str],
    untracked: set[str],
) -> str:
    name = relative.as_posix()
    if name in untracked:
        return "untracked"
    if name in modified:
        return "modified"
    if name in tracked:
        return "tracked"
    return "not-reported-by-git"


def write_source_bundle(files: list[Path]) -> None:
    temporary = SOURCE_OUT.with_suffix(SOURCE_OUT.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as bundle:
        bundle.write("# Sports Federation complete current source bundle\n")
        bundle.write("# Generated for review and patch construction\n\n")
        for relative in files:
            content = read_text(ROOT / relative)
            bundle.write(SEPARATOR + "\n")
            bundle.write(f"FILE: {relative.as_posix()}\n")
            bundle.write(SEPARATOR + "\n\n")
            bundle.write(content)
            if not content.endswith("\n"):
                bundle.write("\n")
            bundle.write("\n")
    os.replace(temporary, SOURCE_OUT)


def build_metadata(
    files: list[Path],
    module_summaries: list[dict],
    existing_modules: list[str],
    missing_modules: list[str],
) -> str:
    tracked, modified, untracked = git_state_sets()
    sections: list[str] = [
        "=== CURRENT BRANCH ===\n"
        + command_output("git", "branch", "--show-current", check=True),
        "=== CURRENT COMMIT ===\n"
        + command_output("git", "rev-parse", "HEAD", check=True),
        "=== REPOSITORY ROOT ===\n" + str(ROOT),
        "=== WORKTREE STATUS ===\n"
        + command_output("git", "status", "--short", "--untracked-files=all"),
        "=== MODULE MANIFESTS ===\n"
        + "\n".join(json.dumps(item, sort_keys=True) for item in module_summaries),
        "=== RELEVANT RECENT HISTORY ===\n"
        + command_output(
            "git", "log", "--oneline", "--decorate", "-30", "--", *existing_modules
        ),
        "=== RECENT REPOSITORY HISTORY ===\n"
        + command_output("git", "log", "--oneline", "--decorate", "-15"),
        "=== UNSTAGED DIFF STAT ===\n" + command_output("git", "diff", "--stat"),
        "=== STAGED DIFF STAT ===\n"
        + command_output("git", "diff", "--cached", "--stat"),
    ]

    sections.append(
        "=== FILE SUMMARY ===\n"
        + "\n".join(
            [
                f"Discovered bundle files: {len(files)}",
                f"Configured modules found: {len(existing_modules)}",
                f"Configured modules missing: {len(missing_modules)}",
                f"Git tracked files: {len(tracked)}",
                f"Git modified or staged files: {len(modified)}",
                f"Git untracked files: {len(untracked)}",
            ]
        )
    )

    inventory = []
    for relative in files:
        path = ROOT / relative
        inventory.append(
            "\t".join(
                [
                    relative.as_posix(),
                    str(path.stat().st_size),
                    sha256_file(path),
                    classify_git_state(relative, tracked, modified, untracked),
                ]
            )
        )
    sections.append("=== BUNDLED FILE INVENTORY ===\n" + "\n".join(inventory))

    if missing_modules:
        sections.append(
            "=== CONFIGURED MODULES NOT FOUND ===\n" + "\n".join(missing_modules)
        )
    return "\n\n".join(sections).rstrip() + "\n"


def main() -> None:
    validate_repository_root()
    existing_modules = discover_addons()
    missing_modules: list[str] = []
    validate_internal_dependencies(existing_modules)
    files = collect_files(existing_modules)
    validate_collection_contract(files)
    summaries = validate_manifest_references(existing_modules, set(files))

    write_source_bundle(files)
    metadata = build_metadata(files, summaries, existing_modules, missing_modules)
    temporary = META_OUT.with_suffix(META_OUT.suffix + ".tmp")
    temporary.write_text(metadata, encoding="utf-8", newline="\n")
    os.replace(temporary, META_OUT)

    print(
        f"Created {SOURCE_OUT.name}: {len(files)} files, "
        f"{SOURCE_OUT.stat().st_size / 1024:.1f} KiB"
    )
    print(
        f"Created {META_OUT.name}: {META_OUT.stat().st_size / 1024:.1f} KiB"
    )
    print("Manifest references validated: OK")
    print("Collector completeness contract: OK")
    if missing_modules:
        print("Warning: configured modules not found: " + ", ".join(missing_modules))


if __name__ == "__main__":
    main()
