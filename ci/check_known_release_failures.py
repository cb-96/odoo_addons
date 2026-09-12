#!/usr/bin/env python3
"""Validate the bounded registry for temporary, known release failures."""

from __future__ import annotations
import argparse, json, re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "ci/contracts/known_release_failures.json"
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CLASSIFICATIONS = {
    "product_defect",
    "migration_defect",
    "test_defect",
    "fixture_defect",
    "documentation_drift",
    "infrastructure_defect",
    "nondeterministic_test",
    "unsupported_configuration",
    "performance_regression",
    "unclassified",
}
REQUIRED = {
    "id",
    "lane",
    "classification",
    "owner",
    "issue_url",
    "test",
    "reason",
    "expires_on",
}


def validate(path: Path, today: date | None = None) -> list[str]:
    today = today or date.today()
    errors = []
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read registry: {exc}"]
    unexpected = sorted(set(document) - {"schema_version", "failures"})
    if unexpected:
        errors.append("unexpected top-level keys: " + ", ".join(unexpected))
    if document.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    failures = document.get("failures")
    if not isinstance(failures, list):
        return errors + ["failures must be a list"]
    seen = set()
    for index, failure in enumerate(failures):
        prefix = f"failures[{index}]"
        if not isinstance(failure, dict):
            errors.append(f"{prefix} must be an object")
            continue
        missing = sorted(REQUIRED - failure.keys())
        extra = sorted(set(failure) - REQUIRED)
        if missing:
            errors.append(f"{prefix} missing: {', '.join(missing)}")
            continue
        if extra:
            errors.append(f"{prefix} has unexpected keys: {', '.join(extra)}")
        fid = failure["id"]
        if not isinstance(fid, str) or not ID_RE.fullmatch(fid):
            errors.append(f"{prefix}.id must be lower-case kebab-case")
        elif fid in seen:
            errors.append(f"{prefix}.id duplicates {fid}")
        seen.add(fid)
        if failure["classification"] not in CLASSIFICATIONS:
            errors.append(f"{prefix}.classification is unsupported")
        if not str(failure["issue_url"]).startswith("https://github.com/"):
            errors.append(f"{prefix}.issue_url must be a GitHub issue URL")
        try:
            expiry = date.fromisoformat(str(failure["expires_on"]))
        except ValueError:
            errors.append(f"{prefix}.expires_on must use YYYY-MM-DD")
        else:
            if expiry < today:
                errors.append(f"{prefix} expired on {expiry.isoformat()}")
        for field in ("lane", "owner", "test", "reason"):
            if not isinstance(failure[field], str) or not failure[field].strip():
                errors.append(f"{prefix}.{field} must be non-empty")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()
    errors = validate(args.registry)
    if errors:
        print("Known release failure registry is invalid:")
        [print(f"- {e}") for e in errors]
        return 1
    count = len(json.loads(args.registry.read_text(encoding="utf-8"))["failures"])
    print(f"Known release failure registry passed ({count} active exceptions).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
