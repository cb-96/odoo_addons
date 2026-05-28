#!/usr/bin/env python3
"""CI guard: portal sudo() calls must have an adjacent ownership scope check.

Every call to .sudo() in portal controller files must be accompanied by at
least one of the following ownership indicators within a ±15-line window:

  - A _portal_* model method call (e.g. _portal_assert_*, _portal_get_*)
  - An explicit portal_privilege or _assert_portal_owns reference
  - A clubs.ids / club_id / team_id scope filter in a domain
  - A user_id / user.id filter (for representative lookups)
  - A clubs = / scope_domain = assignment (proves scope is derived)
  - A # noguard: <reason> comment on the flagged line (explicit exemption)

Files excluded from scanning:
  - portal_privilege.py  (it is the privilege boundary implementation itself)

Exit codes:
  0  all .sudo() calls are guarded
  1  one or more unguarded .sudo() calls found
  2  usage error
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PORTAL_CONTROLLERS = ROOT / "sports_federation_portal" / "controllers"

# Files to exclude (relative to PORTAL_CONTROLLERS)
EXCLUDED_FILES = {"portal_privilege.py"}

# Patterns that indicate a safe ownership scope check
SAFE_PATTERNS = [
    re.compile(r"_portal_"),  # any _portal_* model method
    re.compile(r"portal_privilege"),  # explicit privilege boundary
    re.compile(r"_assert_portal_owns"),
    re.compile(r"portal_assert_in_domain"),
    re.compile(r"clubs\.ids"),  # club scope variable used in domain
    re.compile(r"clubs\s*="),  # club scope being derived
    re.compile(r'"club_id"'),  # club_id domain filter
    re.compile(r"'club_id'"),
    re.compile(r'"team_id"'),  # team_id domain filter
    re.compile(r"'team_id'"),
    re.compile(r'"user_id"'),  # user-scoped representative lookup
    re.compile(r"'user_id'"),
    re.compile(r"user\.id"),
    re.compile(r"scope_domain"),  # explicit scope domain variable
    re.compile(r"portal_club_scope"),
    re.compile(r"portal_team_scope"),
]

SUDO_RE = re.compile(r"\.sudo\(\)")
NOGUARD_RE = re.compile(r"#\s*noguard:")

WINDOW = 15  # lines to check before and after the flagged line (1-indexed offsets)


def has_safe_indicator(lines: list[str], center: int) -> bool:
    """Return True if any safe pattern appears in the window around center."""
    start = max(0, center - WINDOW)
    end = min(len(lines), center + WINDOW + 1)
    window_text = "\n".join(lines[start:end])
    return any(p.search(window_text) for p in SAFE_PATTERNS)


def check_file(path: Path) -> list[tuple[int, str]]:
    """Return a list of (line_number, line_text) for unguarded .sudo() calls."""
    violations: list[tuple[int, str]] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for idx, line in enumerate(lines):
        if not SUDO_RE.search(line):
            continue
        if NOGUARD_RE.search(line):
            continue
        if not has_safe_indicator(lines, idx):
            violations.append((idx + 1, line.rstrip()))
    return violations


def main() -> int:
    if not PORTAL_CONTROLLERS.is_dir():
        print(
            f"[sudo-guard] Portal controllers directory not found: {PORTAL_CONTROLLERS}",
            file=sys.stderr,
        )
        return 2

    all_violations: dict[Path, list[tuple[int, str]]] = {}
    for py_file in sorted(PORTAL_CONTROLLERS.glob("*.py")):
        if py_file.name in EXCLUDED_FILES:
            continue
        violations = check_file(py_file)
        if violations:
            all_violations[py_file] = violations

    if not all_violations:
        print(
            "[sudo-guard] OK — all portal .sudo() calls have an ownership scope check."
        )
        return 0

    print(
        "[sudo-guard] FAIL — the following .sudo() calls lack an adjacent ownership scope check.",
        file=sys.stderr,
    )
    print(
        "[sudo-guard] Add a _portal_*, clubs.ids, or club_id/team_id scope indicator within "
        f"±{WINDOW} lines, or add '# noguard: <reason>' to the flagged line.",
        file=sys.stderr,
    )
    print(file=sys.stderr)
    for path, violations in all_violations.items():
        rel = path.relative_to(ROOT)
        for lineno, text in violations:
            print(f"  {rel}:{lineno}: {text.strip()}", file=sys.stderr)

    return 1


if __name__ == "__main__":
    sys.exit(main())
