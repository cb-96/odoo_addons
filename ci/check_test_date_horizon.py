#!/usr/bin/env python3
"""Keep new expiring dates out of test fixtures.

A fixed date between "today" and the next few decades is a time bomb: written
as "an upcoming match" or "the current season", it silently becomes a past date
and tests fail with no code change. Safe choices are:

- a date in the past, when the test needs a past event;
- a date far in the future (on or after ``FAR_FUTURE``), when it only needs
  to be "later";
- a date relative to the run day (``sports_federation_base/tests/relative_dates``).

The rule is stable over time: a literal counts when it lies between
``BASELINE_DATE`` (the day this rule was introduced) and ``FAR_FUTURE``. The
existing ones are listed per file in ``ci/contracts/test_date_horizon.json``;
the check fails when a file gains more than its baseline, and reports files
whose first counted date is about to pass (warning only). Fix a file, then run
``--update-baseline`` to ratchet the numbers down.

A literal can be exempted with ``# fixed-date: <reason>`` on the same line.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "ci" / "contracts" / "test_date_horizon.json"
BASELINE_DATE = dt.date(2026, 11, 13)
FAR_FUTURE = dt.date(2070, 1, 1)
WARN_DAYS = 45
LITERAL = re.compile(r"""["'](\d{4}-\d{2}-\d{2})(?:[ T]\d{2}:\d{2}(?::\d{2})?)?["']""")
EXEMPT = "fixed-date:"


def scan(root: Path) -> dict[str, list[tuple[dt.date, int]]]:
    found: dict[str, list[tuple[dt.date, int]]] = {}
    for path in sorted(root.glob("sports_federation_*/tests/**/*.py")):
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if EXEMPT in line:
                continue
            for match in LITERAL.finditer(line):
                try:
                    value = dt.date.fromisoformat(match.group(1))
                except ValueError:
                    continue
                if BASELINE_DATE <= value < FAR_FUTURE:
                    found.setdefault(rel, []).append((value, number))
    return found


def load_baseline(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("files", {})


def check(root: Path, baseline: dict[str, int], today: dt.date):
    found = scan(root)
    errors, warnings = [], []
    for rel, literals in sorted(found.items()):
        allowed = baseline.get(rel, 0)
        if len(literals) > allowed:
            lines = ", ".join(
                str(number) for _value, number in sorted(literals, key=lambda x: x[1])
            )
            errors.append(
                f"{rel}: {len(literals)} fixed date(s) between {BASELINE_DATE} and "
                f"{FAR_FUTURE} (baseline {allowed}; lines {lines}). Use a past date, a "
                f"date on or after {FAR_FUTURE}, or relative_dates."
            )
        first = min(value for value, _number in literals)
        if today <= first <= today + dt.timedelta(days=WARN_DAYS):
            warnings.append(
                f"{rel}: fixed date {first} passes in {(first - today).days} day(s)"
            )
    return errors, warnings, found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--today", help="override today (YYYY-MM-DD) for warnings")
    args = parser.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    if args.update_baseline:
        found = scan(ROOT)
        BASELINE.write_text(
            json.dumps(
                {
                    "rule": "fixed test dates between baseline_date and far_future",
                    "baseline_date": BASELINE_DATE.isoformat(),
                    "far_future": FAR_FUTURE.isoformat(),
                    "files": {rel: len(v) for rel, v in sorted(found.items())},
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"Baseline written: {sum(len(v) for v in found.values())} literal(s).")
        return 0

    errors, warnings, found = check(ROOT, load_baseline(BASELINE), today)
    for warning in warnings:
        print(f"warning: {warning}")
    if errors:
        print("Test date horizon check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    total = sum(len(v) for v in found.values())
    print(
        f"Test date horizon check passed ({total} baselined literal(s) left to remove)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
