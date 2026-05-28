#!/usr/bin/env python3
"""Validate local markdown links across repository docs."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SKIP_PREFIXES = ("http://", "https://", "mailto:")
SKIP_DIR_PARTS = {".git", "node_modules", "ci/logs", "__pycache__"}


def _iter_markdown_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.md"):
        rel_parts = set(path.relative_to(ROOT).parts)
        if rel_parts & SKIP_DIR_PARTS:
            continue
        files.append(path)
    return sorted(files)


def _candidate_paths(doc_path: Path, link_target: str) -> list[Path]:
    target = unquote(link_target.strip())
    if not target or target.startswith(SKIP_PREFIXES) or target.startswith("#"):
        return []

    path_text = target.split("#", 1)[0].strip()
    if not path_text:
        return []

    candidates: list[Path] = []
    if path_text.startswith("/"):
        candidates.append(ROOT / path_text.lstrip("/"))
        return candidates

    candidates.append((doc_path.parent / path_text).resolve())

    if path_text.startswith("odoo/"):
        candidates.append((ROOT / path_text[len("odoo/") :]).resolve())

    return candidates


def main() -> int:
    failures: list[str] = []
    for doc_path in _iter_markdown_files():
        rel_doc_path = doc_path.relative_to(ROOT)
        text = doc_path.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK_PATTERN.findall(text):
            if raw_target.startswith(SKIP_PREFIXES) or raw_target.startswith("#"):
                continue

            candidates = _candidate_paths(doc_path, raw_target)
            if not candidates:
                continue

            if any(candidate.exists() for candidate in candidates):
                continue

            failures.append(f"{rel_doc_path}: broken local link target '{raw_target}'")

    if failures:
        print("Markdown link check failed:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("Markdown link check passed for repository docs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
