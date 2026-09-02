#!/usr/bin/env python3
"""Collect the complete Sports Federation source state for review and patching.

Run from the Git repository root containing the Odoo addons:

    python3 source_collector.py

Creates:

    current_sources.txt
    current_sources.jsonl.txt
    current_git_metadata.txt

The text bundle is intended for human review. The JSONL bundle is the
machine-readable source of truth for exact reconstruction and patch generation.
The metadata file records Git state, file modes, hashes, history, and complete
staged and unstaged diffs.

The collector deliberately avoids keyword-based filtering. Every relevant text
source file from the discovered addons and configured repository engineering
directories is included. Manifest data and explicit asset references are
validated before any output file is replaced.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Iterable

ROOT = Path.cwd().resolve()
SOURCE_OUT = ROOT / "current_sources.txt"
JSONL_OUT = ROOT / "current_sources.jsonl.txt"
META_OUT = ROOT / "current_git_metadata.txt"

BUNDLE_FORMAT = "sports-federation-source-bundle"
BUNDLE_FORMAT_VERSION = 3
SEPARATOR = "=" * 100
MAX_TEXT_FILE_SIZE = 10 * 1024 * 1024

# Addons are discovered dynamically. A manual allowlist caused internal
# dependency addons to disappear from review bundles and made full-codebase
# reviews partial.
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
    JSONL_OUT.name,
    META_OUT.name,
    "odoo_addons_code_review.txt",
}

EXCLUDED_PATH_PREFIXES = {
    Path("ci/logs"),
    Path("_logs"),
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
    """Run a repository command and return combined text output."""
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
            f"Command failed with exit code {process.returncode}: "
            f"{' '.join(args)}\n{process.stdout}"
        )
    return process


def command_output(*args: str, check: bool = False) -> str:
    """Return command output without trailing whitespace."""
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
    # back into a newly generated source bundle.
    if path.name.endswith(".patch.txt"):
        return True

    # Never collect interrupted output writes.
    if path.name in {
        SOURCE_OUT.name + ".tmp",
        JSONL_OUT.name + ".tmp",
        META_OUT.name + ".tmp",
    }:
        return True

    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return True

    if any(
        relative == prefix or prefix in relative.parents
        for prefix in EXCLUDED_PATH_PREFIXES
    ):
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
        raise SystemExit(
            f"Refusing to collect path outside repository: {path}"
        ) from exc


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
    """Collect supported root-level files without another hard allowlist."""
    return {
        repository_relative(path)
        for path in ROOT.iterdir()
        if is_supported_text_file(path)
    }


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
            "Manifest is not a dictionary: " f"{manifest_path.relative_to(ROOT)}"
        )
    return manifest


def validate_internal_dependencies(existing_modules: list[str]) -> None:
    """Fail when a collected federation addon depends on an uncollected peer."""
    available = set(existing_modules)
    missing: list[str] = []

    for module in existing_modules:
        manifest = parse_manifest(module)
        for dependency in manifest.get("depends", []):
            if (
                isinstance(dependency, str)
                and dependency.startswith("sports_federation_")
                and dependency not in available
            ):
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
            "Refusing to bundle text file larger than "
            f"{MAX_TEXT_FILE_SIZE} bytes: {path.relative_to(ROOT)}"
        )
    return path.read_text(encoding="utf-8", errors="replace")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
    """Validate manifest data and explicit non-glob asset references."""
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
                errors.append(
                    f"{module}: manifest data file omitted from bundle: {value}"
                )

        assets = manifest.get("assets", {})
        if not isinstance(assets, dict):
            errors.append(f"{module}: manifest assets value is not a dictionary")
            assets = {}

        for bundle_name, entries in assets.items():
            if not isinstance(entries, (list, tuple)):
                errors.append(
                    f"{module}: asset bundle {bundle_name!r} " "is not a list or tuple"
                )
                continue

            for entry in entries:
                if not isinstance(entry, str):
                    continue

                relative = explicit_asset_path(module, entry)
                if relative is None:
                    continue

                explicit_assets.append(entry)
                path = ROOT / relative

                # Explicit, non-glob assets must exist. Do not maintain a stale
                # asset exception list, because Odoo will still try to load the
                # missing manifest reference.
                if not path.is_file():
                    errors.append(f"{module}: missing explicit asset file: {entry}")
                elif is_supported_text_file(path) and relative not in bundled_files:
                    errors.append(
                        f"{module}: explicit asset omitted from bundle: {entry}"
                    )

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


def git_file_modes() -> dict[str, str]:
    """Return index modes keyed by repository-relative path."""
    process = subprocess.run(
        ("git", "ls-files", "-s", "-z"),
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.returncode:
        return {}

    modes: dict[str, str] = {}
    for entry in process.stdout.split(b"\0"):
        if not entry or b"\t" not in entry:
            continue

        metadata, raw_path = entry.split(b"\t", 1)
        mode = metadata.split(b" ", 1)[0].decode("ascii", errors="replace")
        path = raw_path.decode("utf-8", errors="replace")
        modes[path] = mode

    return modes


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


def expected_git_mode(relative: Path, modes: dict[str, str]) -> str:
    """Return the tracked mode or the safe default for a new text file."""
    return modes.get(relative.as_posix(), "100644")


def filesystem_mode(path: Path) -> str:
    return f"{path.stat().st_mode & 0o777:04o}"


def build_file_record(
    relative: Path,
    tracked: set[str],
    modified: set[str],
    untracked: set[str],
    modes: dict[str, str],
) -> dict:
    path = ROOT / relative
    raw = path.read_bytes()
    content = raw.decode("utf-8", errors="replace")

    return {
        "path": relative.as_posix(),
        "content": content,
        "content_length": len(content),
        "size_bytes": len(raw),
        "sha256": sha256_bytes(raw),
        "git_mode": expected_git_mode(relative, modes),
        "filesystem_mode": filesystem_mode(path),
        "git_state": classify_git_state(
            relative,
            tracked,
            modified,
            untracked,
        ),
    }


def write_source_bundle(records: list[dict]) -> None:
    temporary = SOURCE_OUT.with_suffix(SOURCE_OUT.suffix + ".tmp")

    with temporary.open("w", encoding="utf-8", newline="\n") as bundle:
        bundle.write("# Sports Federation complete current source bundle\n")
        bundle.write("# Generated for review and patch construction\n")
        bundle.write(f"# FORMAT: {BUNDLE_FORMAT}\n")
        bundle.write(f"# FORMAT-VERSION: {BUNDLE_FORMAT_VERSION}\n")
        bundle.write(f"# SEPARATOR-LENGTH: {len(SEPARATOR)}\n")
        bundle.write(f"# FILE-COUNT: {len(records)}\n\n")

        for record in records:
            bundle.write(SEPARATOR + "\n")
            bundle.write(f"FILE: {record['path']}\n")
            bundle.write(f"SIZE: {record['size_bytes']}\n")
            bundle.write(f"CONTENT-LENGTH: {record['content_length']}\n")
            bundle.write(f"SHA256: {record['sha256']}\n")
            bundle.write(f"GIT-MODE: {record['git_mode']}\n")
            bundle.write(f"FILESYSTEM-MODE: {record['filesystem_mode']}\n")
            bundle.write(f"GIT-STATE: {record['git_state']}\n")
            bundle.write(SEPARATOR + "\n\n")
            bundle.write(record["content"])
            if not record["content"].endswith("\n"):
                bundle.write("\n")
            bundle.write("\n")

    os.replace(temporary, SOURCE_OUT)


def write_jsonl_bundle(records: list[dict]) -> None:
    temporary = JSONL_OUT.with_suffix(JSONL_OUT.suffix + ".tmp")

    with temporary.open("w", encoding="utf-8", newline="\n") as bundle:
        metadata_record = {
            "record_type": "bundle_metadata",
            "format": BUNDLE_FORMAT,
            "format_version": BUNDLE_FORMAT_VERSION,
            "repository_root": str(ROOT),
            "file_count": len(records),
        }
        bundle.write(
            json.dumps(metadata_record, ensure_ascii=False, sort_keys=True) + "\n"
        )

        for record in records:
            output = {"record_type": "file", **record}
            bundle.write(json.dumps(output, ensure_ascii=False, sort_keys=True) + "\n")

    os.replace(temporary, JSONL_OUT)


def parse_text_bundle(path: Path) -> list[dict]:
    """Parse the generated text format for round-trip validation.

    CONTENT-LENGTH defines the exact logical-content boundary. Bundle framing
    newlines therefore never become part of source content, regardless of
    whether the original file ended with LF, CRLF, multiple blank lines, or no
    newline at all.
    """
    with path.open(
        "r",
        encoding="utf-8",
        errors="replace",
        newline="",
    ) as source:
        text = source.read()

    header_pattern = re.compile(
        rf"^{re.escape(SEPARATOR)}\n"
        r"FILE: (?P<path>.+)\n"
        r"SIZE: (?P<size>\d+)\n"
        r"CONTENT-LENGTH: (?P<content_length>\d+)\n"
        r"SHA256: (?P<sha256>[0-9a-f]{64})\n"
        r"GIT-MODE: (?P<git_mode>\d{6})\n"
        r"FILESYSTEM-MODE: (?P<filesystem_mode>\d{4})\n"
        r"GIT-STATE: (?P<git_state>[^\n]+)\n"
        rf"{re.escape(SEPARATOR)}\n\n",
        flags=re.MULTILINE,
    )

    parsed: list[dict] = []
    position = 0

    while True:
        match = header_pattern.search(text, position)
        if match is None:
            break

        content_start = match.end()
        content_length = int(match.group("content_length"))
        content_end = content_start + content_length

        if content_end > len(text):
            raise SystemExit(
                "Generated text bundle contains truncated content for "
                f"{match.group('path')}: expected {content_length} "
                f"characters, only {len(text) - content_start} available."
            )

        content = text[content_start:content_end]

        parsed.append(
            {
                "path": match.group("path"),
                "content": content,
                "content_length": content_length,
                "size_bytes": int(match.group("size")),
                "sha256": match.group("sha256"),
                "git_mode": match.group("git_mode"),
                "filesystem_mode": match.group("filesystem_mode"),
                "git_state": match.group("git_state"),
            }
        )

        # Start after the exact source content. The next search skips only the
        # bundle framing newline or newlines inserted by write_source_bundle().
        position = content_end

    return parsed


def validate_written_bundles(records: list[dict]) -> None:
    """Read generated bundles back and verify identity and content."""
    text_records = parse_text_bundle(SOURCE_OUT)

    with JSONL_OUT.open("r", encoding="utf-8") as source:
        jsonl_records = [json.loads(line) for line in source if line.strip()]

    if not jsonl_records:
        raise SystemExit("Generated JSONL bundle is empty.")

    metadata = jsonl_records[0]
    if metadata.get("record_type") != "bundle_metadata":
        raise SystemExit("Generated JSONL bundle is missing metadata.")

    jsonl_files = [
        {key: value for key, value in item.items() if key != "record_type"}
        for item in jsonl_records[1:]
        if item.get("record_type") == "file"
    ]

    expected_paths = [record["path"] for record in records]
    text_paths = [record["path"] for record in text_records]
    jsonl_paths = [record["path"] for record in jsonl_files]

    if text_paths != expected_paths:
        raise SystemExit(
            "Generated text bundle failed path/order round-trip validation."
        )
    if jsonl_paths != expected_paths:
        raise SystemExit(
            "Generated JSONL bundle failed path/order round-trip validation."
        )

    expected_by_path = {record["path"]: record for record in records}
    text_by_path = {record["path"]: record for record in text_records}
    jsonl_by_path = {record["path"]: record for record in jsonl_files}

    for path, expected in expected_by_path.items():
        text_record = text_by_path[path]
        jsonl_record = jsonl_by_path[path]

        # Text-mode newline handling can normalize the final separator newline,
        # so compare the exact logical content and all declared metadata.
        if text_record["content"] != expected["content"]:
            raise SystemExit(f"Text bundle content mismatch after round trip: {path}")

        for field in (
            "size_bytes",
            "sha256",
            "git_mode",
            "filesystem_mode",
            "git_state",
        ):
            if text_record[field] != expected[field]:
                raise SystemExit(
                    f"Text bundle {field} mismatch after round trip: {path}"
                )

        if jsonl_record != expected:
            raise SystemExit(f"JSONL bundle mismatch after round trip: {path}")


def build_metadata(
    files: list[Path],
    records: list[dict],
    module_summaries: list[dict],
    existing_modules: list[str],
    missing_modules: list[str],
    tracked: set[str],
    modified: set[str],
    untracked: set[str],
) -> str:
    sections: list[str] = [
        "=== BUNDLE FORMAT ===\n"
        + "\n".join(
            [
                f"Format: {BUNDLE_FORMAT}",
                f"Format version: {BUNDLE_FORMAT_VERSION}",
                f"Text separator length: {len(SEPARATOR)}",
                f"Source bundle: {SOURCE_OUT.name}",
                f"Machine bundle: {JSONL_OUT.name}",
            ]
        ),
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
            "git",
            "log",
            "--oneline",
            "--decorate",
            "-30",
            "--",
            *existing_modules,
        ),
        "=== RECENT REPOSITORY HISTORY ===\n"
        + command_output("git", "log", "--oneline", "--decorate", "-15"),
        "=== UNSTAGED DIFF STAT ===\n" + command_output("git", "diff", "--stat"),
        "=== STAGED DIFF STAT ===\n"
        + command_output("git", "diff", "--cached", "--stat"),
        "=== UNSTAGED DIFF ===\n"
        + command_output(
            "git",
            "diff",
            "--binary",
            "--full-index",
            "--no-ext-diff",
        ),
        "=== STAGED DIFF ===\n"
        + command_output(
            "git",
            "diff",
            "--cached",
            "--binary",
            "--full-index",
            "--no-ext-diff",
        ),
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
    for record in records:
        inventory.append(
            "\t".join(
                [
                    record["path"],
                    str(record["size_bytes"]),
                    record["sha256"],
                    record["git_mode"],
                    record["filesystem_mode"],
                    record["git_state"],
                ]
            )
        )

    sections.append(
        "=== BUNDLED FILE INVENTORY ===\n"
        "# path<TAB>size<TAB>sha256<TAB>git-mode"
        "<TAB>filesystem-mode<TAB>git-state\n" + "\n".join(inventory)
    )

    if missing_modules:
        sections.append(
            "=== CONFIGURED MODULES NOT FOUND ===\n" + "\n".join(missing_modules)
        )

    return "\n\n".join(sections).rstrip() + "\n"


def write_metadata(content: str) -> None:
    temporary = META_OUT.with_suffix(META_OUT.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temporary, META_OUT)


def main() -> None:
    validate_repository_root()

    existing_modules = discover_addons()
    missing_modules: list[str] = []

    validate_internal_dependencies(existing_modules)

    files = collect_files(existing_modules)
    validate_collection_contract(files)
    summaries = validate_manifest_references(existing_modules, set(files))

    tracked, modified, untracked = git_state_sets()
    modes = git_file_modes()
    records = [
        build_file_record(
            relative,
            tracked,
            modified,
            untracked,
            modes,
        )
        for relative in files
    ]

    write_source_bundle(records)
    write_jsonl_bundle(records)
    validate_written_bundles(records)

    metadata = build_metadata(
        files,
        records,
        summaries,
        existing_modules,
        missing_modules,
        tracked,
        modified,
        untracked,
    )
    write_metadata(metadata)

    print(
        f"Created {SOURCE_OUT.name}: {len(files)} files, "
        f"{SOURCE_OUT.stat().st_size / 1024:.1f} KiB"
    )
    print(
        f"Created {JSONL_OUT.name}: {len(files)} files, "
        f"{JSONL_OUT.stat().st_size / 1024:.1f} KiB"
    )
    print(f"Created {META_OUT.name}: " f"{META_OUT.stat().st_size / 1024:.1f} KiB")
    print("Manifest references validated: OK")
    print("Collector completeness contract: OK")
    print("Bundle round-trip validation: OK")

    if missing_modules:
        print("Warning: configured modules not found: " + ", ".join(missing_modules))


if __name__ == "__main__":
    main()
