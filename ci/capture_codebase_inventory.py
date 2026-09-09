#!/usr/bin/env python3
"""Create a deterministic inventory of security and architecture hotspots.

The inventory is evidence, not a policy gate. It gives reviewers one stable list
of addons, routes, elevated calls, raw SQL, scheduled jobs, migrations, and large
Python files for the exact candidate being qualified.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

DEFAULT_LARGE_FILE_LINES = 500
ROUTE_RE = re.compile(r"@(?:http\.)?route\s*\(")
SUDO_RE = re.compile(r"\.sudo\s*\(")
SQL_RE = re.compile(
    r"(?:\.execute\s*\(|\b(?:SELECT|INSERT|UPDATE|DELETE|ALTER|CREATE|DROP)\b)", re.I
)
CRON_RE = re.compile(r"<record\b[^>]*\bmodel=[\"']ir\.cron[\"']", re.I)
MODEL_NAME_RE = re.compile(r"^\s*_(?:name|inherit)\s*=\s*[\"']([^\"']+)[\"']", re.M)


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def discover_addons(repo: Path) -> list[Path]:
    return sorted(
        path.parent
        for path in repo.glob("sports_federation_*/__manifest__.py")
        if path.is_file()
    )


def parse_manifest(path: Path) -> dict:
    try:
        value = ast.literal_eval(path.read_text(encoding="utf-8"))
    except (SyntaxError, ValueError) as exc:
        raise SystemExit(f"Invalid manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SystemExit(f"Manifest is not a dictionary: {path}")
    return value


def location(repo: Path, path: Path, lineno: int, text: str = "") -> dict:
    item = {"path": path.relative_to(repo).as_posix(), "line": lineno}
    if text:
        item["text"] = text.strip()[:240]
    return item


def scan_python(repo: Path, path: Path, large_file_lines: int, result: dict) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) >= large_file_lines:
        result["large_python_files"].append(
            {**location(repo, path, 1), "lines": len(lines)}
        )
    for lineno, line in enumerate(lines, 1):
        if SUDO_RE.search(line):
            result["sudo_calls"].append(location(repo, path, lineno, line))
        if SQL_RE.search(line) and not line.lstrip().startswith("#"):
            result["raw_sql_candidates"].append(location(repo, path, lineno, line))
        if ROUTE_RE.search(line):
            block = " ".join(lines[lineno - 1 : min(lineno + 9, len(lines))])
            result["routes"].append(
                {
                    **location(repo, path, lineno, line),
                    "auth": _keyword(block, "auth"),
                    "csrf": _keyword(block, "csrf"),
                    "methods": _keyword(block, "methods"),
                }
            )
    for model in MODEL_NAME_RE.findall(text):
        result["model_declarations"].append(
            {"path": path.relative_to(repo).as_posix(), "model": model}
        )


def _keyword(block: str, name: str):
    match = re.search(rf"\b{name}\s*=\s*([^,\)]+)", block)
    return match.group(1).strip() if match else None


def build_inventory(repo: Path, large_file_lines: int) -> dict:
    addons = discover_addons(repo)
    result = {
        "schema_version": 1,
        "commit": git(repo, "rev-parse", "HEAD"),
        "addons": [],
        "routes": [],
        "sudo_calls": [],
        "raw_sql_candidates": [],
        "scheduled_jobs": [],
        "migrations": [],
        "model_declarations": [],
        "large_python_files": [],
    }
    for addon in addons:
        manifest = parse_manifest(addon / "__manifest__.py")
        result["addons"].append(
            {
                "name": addon.name,
                "version": manifest.get("version"),
                "depends": sorted(manifest.get("depends", [])),
                "installable": bool(manifest.get("installable", True)),
            }
        )
    roots = addons + [repo / "ci", repo / "scripts"]
    files = sorted(
        {
            path
            for root in roots
            if root.exists()
            for path in root.rglob("*")
            if path.is_file()
        }
    )
    for path in files:
        rel = path.relative_to(repo).as_posix()
        if path.suffix == ".py":
            scan_python(repo, path, large_file_lines, result)
        elif path.suffix == ".xml":
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in CRON_RE.finditer(text):
                result["scheduled_jobs"].append(
                    location(repo, path, text.count("\n", 0, match.start()) + 1)
                )
        if "/migrations/" in f"/{rel}" and path.suffix in {".py", ".sql"}:
            result["migrations"].append(rel)
    for key in (
        "routes",
        "sudo_calls",
        "raw_sql_candidates",
        "scheduled_jobs",
        "model_declarations",
        "large_python_files",
    ):
        result[key] = sorted(
            result[key],
            key=lambda item: (item["path"], item.get("line", 0), item.get("model", "")),
        )
    result["migrations"].sort()
    canonical = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    result["inventory_sha256"] = hashlib.sha256(canonical).hexdigest()
    result["counts"] = {
        "addons": len(result["addons"]),
        "routes": len(result["routes"]),
        "sudo_calls": len(result["sudo_calls"]),
        "raw_sql_candidates": len(result["raw_sql_candidates"]),
        "scheduled_jobs": len(result["scheduled_jobs"]),
        "migrations": len(result["migrations"]),
        "model_declarations": len(result["model_declarations"]),
        "large_python_files": len(result["large_python_files"]),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--large-file-lines", type=int, default=DEFAULT_LARGE_FILE_LINES
    )
    args = parser.parse_args()
    repo = args.repo.resolve()
    inventory = build_inventory(repo, args.large_file_lines)
    output = args.output if args.output.is_absolute() else repo / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
