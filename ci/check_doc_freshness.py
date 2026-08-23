#!/usr/bin/env python3

from datetime import date, datetime
import os
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "ci" / "contracts" / "documentation_freshness.json"


def load_tracked_docs() -> list[str]:
    if not CONTRACT_PATH.is_file():
        raise FileNotFoundError(
            f"documentation freshness contract is missing: {CONTRACT_PATH}"
        )
    data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    documents = data.get("documents")
    if not isinstance(documents, list) or not all(
        isinstance(item, str) for item in documents
    ):
        raise ValueError(
            "documentation freshness contract must contain a string list named 'documents'"
        )
    return documents


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
    try:
        tracked_docs = load_tracked_docs()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Documentation freshness check failed: {exc}")
        return 2

    for rel_path in tracked_docs:
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
    for rel_path in tracked_docs:
        print(f" - {rel_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
