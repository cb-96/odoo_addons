#!/usr/bin/env python3

from datetime import date, datetime
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
TRACKED_DOCS = [
    "CODE_REVIEW_REPORT.md",
    "MAINTAINABILITY_REVIEW.md",
    "ROADMAP.md",
    "TECHNICAL_NOTE.md",
    "CONTEXT.md",
    "INTEGRATIONS.md",
    "INTEGRATION_CONTRACTS.md",
    "ROUTE_INVENTORY.md",
    "STATE_AND_OWNERSHIP_MATRIX.md",
    "RELEASE_RUNBOOK.md",
    "RELEASE_TRAIN.md",
    "DATA_RETENTION_POLICY.md",
    "RESTORE_VERIFICATION_CHECKLIST.md",
    "adr/README.md",
    "adr/0001-portal-trust-boundaries.md",
    "adr/0002-reporting-sql-views.md",
    "adr/0003-public-route-ownership.md",
]
REQUIRED_FIELDS = ("Owner", "Last reviewed", "Review cadence")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_AGE_DAYS_BY_CADENCE = {
    "Every release": 120,
}


def read_metadata(path: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines()[:12]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()
    return metadata


def get_today() -> date:
    override = os.environ.get("DOC_FRESHNESS_TODAY", "").strip()
    if override:
        return datetime.strptime(override, "%Y-%m-%d").date()
    return date.today()


def main() -> int:
    failures: list[str] = []
    today = get_today()

    for rel_path in TRACKED_DOCS:
        path = ROOT / rel_path
        if not path.exists():
            failures.append(f"{rel_path}: file is missing")
            continue

        metadata = read_metadata(path)
        for field in REQUIRED_FIELDS:
            if not metadata.get(field):
                failures.append(
                    f"{rel_path}: missing '{field}:' metadata near the top of the file"
                )

        last_reviewed = metadata.get("Last reviewed")
        if last_reviewed and not DATE_PATTERN.match(last_reviewed):
            failures.append(
                f"{rel_path}: 'Last reviewed' must use YYYY-MM-DD, found '{last_reviewed}'"
            )
            continue

        review_cadence = metadata.get("Review cadence")
        max_age_days = MAX_AGE_DAYS_BY_CADENCE.get(review_cadence or "")
        if last_reviewed and max_age_days is not None:
            reviewed_on = datetime.strptime(last_reviewed, "%Y-%m-%d").date()
            age_days = (today - reviewed_on).days
            if age_days > max_age_days:
                failures.append(
                    f"{rel_path}: last reviewed {age_days} days ago, exceeds {max_age_days}-day freshness budget for '{review_cadence}'"
                )

    if failures:
        print("Documentation freshness check failed:")
        for failure in failures:
            print(f" - {failure}")
        return 1

    print("Documentation freshness metadata is present for tracked docs:")
    for rel_path in TRACKED_DOCS:
        print(f" - {rel_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
