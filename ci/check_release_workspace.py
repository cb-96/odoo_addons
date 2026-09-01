#!/usr/bin/env python3
"""Fail release qualification when repository state is not reproducible."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED_PATTERNS = (
    "ci/odoo-ci.generated.conf.*",
    "ci/odoo-ci.generated.runtime.conf",
)


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=False,
        text=True,
        capture_output=True,
    )


def main() -> int:
    if not (ROOT / ".git").exists():
        print("Release workspace check skipped: no Git checkout metadata.")
        return 0

    diff_check = git("diff", "--check")
    if diff_check.returncode:
        print(diff_check.stdout or diff_check.stderr, file=sys.stderr)
        return 1

    tracked_changes = git("status", "--porcelain", "--untracked-files=no")
    if tracked_changes.returncode:
        print(tracked_changes.stderr, file=sys.stderr)
        return tracked_changes.returncode
    if tracked_changes.stdout.strip():
        print("Release workspace contains tracked changes:", file=sys.stderr)
        print(tracked_changes.stdout, file=sys.stderr)
        return 1

    generated = sorted(
        path.relative_to(ROOT).as_posix()
        for pattern in GENERATED_PATTERNS
        for path in ROOT.glob(pattern)
    )
    if generated:
        print("Generated runtime configuration is present:", file=sys.stderr)
        for path in generated:
            print(f"- {path}", file=sys.stderr)
        return 1

    print("Release workspace is clean and reproducible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
