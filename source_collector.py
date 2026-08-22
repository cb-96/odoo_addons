#!/usr/bin/env python3
"""Collect the full Sports Federation source tree for review and patching.

Run this script from the Git repository root containing the Odoo addons:

    python3 collect_current_sources.py

Creates:

    current_sources.txt
    current_git_metadata.txt

Design goals:

* Include every relevant text source file from every configured addon.
* Never use content or keyword filtering.
* Preserve the simple FILE bundle format used by review tooling.
* Validate manifest data and explicit asset references.
* Record file sizes, SHA256 hashes, and Git state in the metadata file.
* Fail rather than silently produce an incomplete patch baseline.
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

MODULES = [
    "sports_federation_base",
    "sports_federation_calendar",
    "sports_federation_format",
    "sports_federation_scheduling",
    "sports_federation_registration",
    "sports_federation_competition_core",
    "sports_federation_schedule_approval",
    "sports_federation_matchday",
    "sports_federation_rules",
    "sports_federation_tournament",
    "sports_federation_competition_engine",
    "sports_federation_officiating",
    "sports_federation_result_control",
    "sports_federation_portal",
    "sports_federation_notifications",
]

# All source-like text formats used by Odoo addons, CI, documentation, and tests.
TEXT_EXTENSIONS = {
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
}

# Repository-level files/directories that materially affect builds and reviews.
REPOSITORY_FILES = [
    ".gitignore",
    ".pre-commit-config.yaml",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "Dockerfile",
    "LICENSE",
    "Makefile",
    "README.md",
    "ROADMAP.md",
    "SECURITY.md",
    "docker-compose.yml",
    "pyproject.toml",
    "requirements-dev.txt",
    "requirements.txt",
    "ruff.toml",
]

REPOSITORY_DIRECTORIES = [
    ".github",
    "ci",
    "docs",
    "scripts",
]

# Avoid accidentally embedding huge generated text artifacts.
MAX_TEXT_FILE_SIZE = 10 * 1024 * 1024


def run(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a command from the repository root."""

    process = subprocess.run(
        args,
        cwd=ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if check and process.returncode:
        command = " ".join(args)
        raise SystemExit(
            f"Command failed with exit code {process.returncode}: {command}\n"
            f"{process.stdout}"
        )
    return process


def command_output(*args: str, check: bool = False) -> str:
    """Return normalized command output."""

    return run(*args, check=check).stdout.rstrip()


def validate_repository_root() -> None:
    """Ensure the script is running from the intended Git repository root."""

    if command_output("git", "rev-parse", "--show-toplevel") != str(ROOT):
        raise SystemExit("Run this script from the Git repository root.")

    required = [
        ROOT / "sports_federation_base",
        ROOT / "sports_federation_competition_engine",
    ]
    missing = [path.name for path in required if not path.is_dir()]
    if missing:
        raise SystemExit(
            "Repository validation failed. Missing required addon directories: "
            + ", ".join(missing)
        )


def is_excluded(path: Path) -> bool:
    """Return whether a repository-relative path must be excluded."""

    if path.name in EXCLUDED_FILENAMES:
        return True
    return any(part in EXCLUDED_DIRECTORY_NAMES for part in path.parts)


def is_supported_text_file(path: Path) -> bool:
    """Return whether a file belongs in the source bundle."""

    if not path.is_file() or is_excluded(path):
        return False
    if path.name in TEXT_FILENAMES:
        return True
    return path.suffix.lower() in TEXT_EXTENSIONS


def repository_relative(path: Path) -> Path:
    """Resolve and validate a repository-relative path."""

    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT)
    except ValueError as exc:
        raise SystemExit(f"Refusing to collect path outside repository: {path}") from exc


def collect_directory(directory: Path) -> set[Path]:
    """Collect all supported text files recursively below a directory."""

    files: set[Path] = set()
    if not directory.is_dir():
        return files

    for path in directory.rglob("*"):
        if is_supported_text_file(path):
            files.add(repository_relative(path))
    return files


def collect_files(existing_modules: Iterable[str]) -> list[Path]:
    """Collect the complete configured addon and repository source set."""

    files: set[Path] = set()

    for module in existing_modules:
        files.update(collect_directory(ROOT / module))

    for filename in REPOSITORY_FILES:
        path = ROOT / filename
        if is_supported_text_file(path):
            files.add(repository_relative(path))

    for directory in REPOSITORY_DIRECTORIES:
        files.update(collect_directory(ROOT / directory))

    return sorted(files, key=lambda path: path.as_posix())


def read_text(path: Path) -> str:
    """Read one bounded text file using stable replacement handling."""

    size = path.stat().st_size
    if size > MAX_TEXT_FILE_SIZE:
        raise SystemExit(
            f"Refusing to bundle text file larger than {MAX_TEXT_FILE_SIZE} bytes: "
            f"{path.relative_to(ROOT)}"
        )
    return path.read_text(encoding="utf-8", errors="replace")


def sha256_file(path: Path) -> str:
    """Return the SHA256 digest for a file."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_manifest(module: str) -> dict:
    """Parse an Odoo manifest safely without importing it."""

    manifest_path = ROOT / module / "__manifest__.py"
    if not manifest_path.is_file():
        raise SystemExit(f"Missing manifest: {manifest_path.relative_to(ROOT)}")

    try:
        manifest = ast.literal_eval(
            manifest_path.read_text(encoding="utf-8", errors="strict")
        )
    except (SyntaxError, ValueError, UnicodeError) as exc:
        raise SystemExit(
            f"Cannot parse {manifest_path.relative_to(ROOT)}: {exc}"
        ) from exc

    if not isinstance(manifest, dict):
        raise SystemExit(
            f"Manifest is not a dictionary: {manifest_path.relative_to(ROOT)}"
        )
    return manifest


def expand_explicit_asset_path(module: str, value: str) -> Path | None:
    """Return a local explicit asset path, ignoring globs and external assets."""

    if not value or any(character in value for character in "*?["):
        return None

    prefix = module + "/"
    if not value.startswith(prefix):
        return None

    return Path(module) / value[len(prefix) :]


def validate_manifest_references(
    existing_modules: list[str], bundled_files: set[Path]
) -> list[dict]:
    """Validate manifest data/assets and ensure referenced text files are bundled."""

    errors: list[str] = []
    summaries: list[dict] = []

    for module in existing_modules:
        manifest = parse_manifest(module)
        module_root = ROOT / module

        referenced_data: list[str] = []
        for value in manifest.get("data", []):
            if not isinstance(value, str):
                errors.append(f"{module}: non-string manifest data entry: {value!r}")
                continue

            referenced_data.append(value)
            path = module_root / value
            relative = Path(module) / value

            if not path.is_file():
                errors.append(f"{module}: missing manifest data file: {value}")
            elif is_supported_text_file(path) and relative not in bundled_files:
                errors.append(f"{module}: manifest data file omitted from bundle: {value}")

        explicit_assets: list[str] = []
        for bundle_name, entries in manifest.get("assets", {}).items():
            if not isinstance(entries, (list, tuple)):
                errors.append(
                    f"{module}: asset bundle {bundle_name!r} is not a list or tuple"
                )
                continue

            for entry in entries:
                # Odoo assets may use tuples such as ('include', bundle).
                if not isinstance(entry, str):
                    continue

                asset_relative = expand_explicit_asset_path(module, entry)
                if asset_relative is None:
                    continue

                explicit_assets.append(entry)
                asset_path = ROOT / asset_relative
                if not asset_path.is_file():
                    errors.append(f"{module}: missing explicit asset file: {entry}")
                elif is_supported_text_file(asset_path) and asset_relative not in bundled_files:
                    errors.append(f"{module}: explicit asset omitted from bundle: {entry}")

        summaries.append(
            {
                "module": module,
                "name": manifest.get("name"),
                "version": manifest.get("version"),
                "depends": manifest.get("depends", []),
                "data": referenced_data,
                "explicit_assets": explicit_assets,
                "installable": manifest.get("installable", True),
                "application": manifest.get("application", False),
                "auto_install": manifest.get("auto_install", False),
            }
        )

    if errors:
        formatted = "\n".join(f"  - {error}" for error in errors)
        raise SystemExit(
            "Manifest/source validation failed. The bundle was not written:\n"
            + formatted
        )

    return summaries


def nul_git_paths(*args: str) -> set[str]:
    """Return paths from a NUL-separated Git command."""

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
    """Return tracked, modified/staged, and untracked path sets."""

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
    """Classify a bundled file using Git's repository state."""

    name = relative.as_posix()
    if name in untracked:
        return "untracked"
    if name in modified:
        return "modified"
    if name in tracked:
        return "tracked"
    return "not-reported-by-git"


def write_source_bundle(files: list[Path]) -> None:
    """Write the intentionally simple FILE/SEPARATOR source bundle."""

    temporary = SOURCE_OUT.with_suffix(SOURCE_OUT.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as bundle:
        bundle.write("# Sports Federation complete current source bundle\n")
        bundle.write("# Generated for review and patch construction\n\n")

        for relative in files:
            path = ROOT / relative
            content = read_text(path)

            # Keep this exact structure for compatibility with bundle readers.
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
    """Build detailed repository and source-bundle metadata."""

    tracked, modified, untracked = git_state_sets()

    sections: list[str] = []
    sections.append(
        "=== CURRENT BRANCH ===\n"
        + command_output("git", "branch", "--show-current", check=True)
    )
    sections.append(
        "=== CURRENT COMMIT ===\n"
        + command_output("git", "rev-parse", "HEAD", check=True)
    )
    sections.append("=== REPOSITORY ROOT ===\n" + str(ROOT))
    sections.append(
        "=== WORKTREE STATUS ===\n"
        + command_output("git", "status", "--short", "--untracked-files=all")
    )
    sections.append(
        "=== MODULE MANIFESTS ===\n"
        + "\n".join(json.dumps(item, sort_keys=True) for item in module_summaries)
    )
    sections.append(
        "=== RELEVANT RECENT HISTORY ===\n"
        + command_output(
            "git",
            "log",
            "--oneline",
            "--decorate",
            "-30",
            "--",
            *existing_modules,
        )
    )
    sections.append(
        "=== RECENT REPOSITORY HISTORY ===\n"
        + command_output("git", "log", "--oneline", "--decorate", "-15")
    )
    sections.append(
        "=== UNSTAGED DIFF STAT ===\n" + command_output("git", "diff", "--stat")
    )
    sections.append(
        "=== STAGED DIFF STAT ===\n"
        + command_output("git", "diff", "--cached", "--stat")
    )

    summary_lines = [
        f"Discovered bundle files: {len(files)}",
        f"Configured modules found: {len(existing_modules)}",
        f"Configured modules missing: {len(missing_modules)}",
        f"Git tracked files: {len(tracked)}",
        f"Git modified or staged files: {len(modified)}",
        f"Git untracked files: {len(untracked)}",
    ]
    sections.append("=== FILE SUMMARY ===\n" + "\n".join(summary_lines))

    inventory: list[str] = []
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
    """Collect and validate the full source bundle."""

    validate_repository_root()

    existing_modules = [module for module in MODULES if (ROOT / module).is_dir()]
    missing_modules = [module for module in MODULES if not (ROOT / module).is_dir()]

    files = collect_files(existing_modules)
    bundled_set = set(files)

    # This is deliberately before writing output. Never publish a partial bundle.
    module_summaries = validate_manifest_references(existing_modules, bundled_set)

    write_source_bundle(files)

    metadata = build_metadata(
        files,
        module_summaries,
        existing_modules,
        missing_modules,
    )
    temporary_metadata = META_OUT.with_suffix(META_OUT.suffix + ".tmp")
    temporary_metadata.write_text(metadata, encoding="utf-8", newline="\n")
    os.replace(temporary_metadata, META_OUT)

    print(
        f"Created {SOURCE_OUT.name}: {len(files)} files, "
        f"{SOURCE_OUT.stat().st_size / 1024:.1f} KiB"
    )
    print(
        f"Created {META_OUT.name}: "
        f"{META_OUT.stat().st_size / 1024:.1f} KiB"
    )
    print("Manifest references validated: OK")

    if missing_modules:
        print(
            "Warning: configured modules not found: " + ", ".join(missing_modules)
        )


if __name__ == "__main__":
    main()
