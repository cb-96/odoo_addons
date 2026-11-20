#!/usr/bin/env python3
"""Protect isolated release evidence and automatic failure classification."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ci/run_release_baseline.sh"
CLASSIFIER = ROOT / "ci/classify_release_failure.py"


def find_violations(root: Path = ROOT) -> list[str]:
    script = root / SCRIPT.relative_to(ROOT)
    classifier = root / CLASSIFIER.relative_to(ROOT)
    if not script.is_file():
        return ["release baseline script is missing"]
    source = script.read_text()
    violations = []
    if "artifacts/release/baseline" not in source:
        violations.append(
            "default release evidence is not under artifacts/release/baseline"
        )
    if "Evidence directory must be outside the repository" not in source:
        violations.append("release evidence outside artifacts/release is not rejected")
    preflight_gate = source.find("if (( preflight_blocked )); then")
    run_lane = source.find('run_lane "$lane"')
    if (
        "preflight_blocked=0" not in source
        or "record_skipped_lane" not in source
        or preflight_gate < 0
        or run_lane < preflight_gate
        or "continue" not in source[preflight_gate:run_lane]
    ):
        violations.append("failed preflight does not block the remaining lanes")
    preparation_failure = source.find("if (( prepare_exit_code != 0 )); then")
    if (
        '"scripts/ci/run_rc_validation.sh prepare-upgrade"' not in source
        or preparation_failure < 0
        or run_lane < preparation_failure
        or "continue" not in source[preparation_failure:run_lane]
    ):
        violations.append(
            "upgrade does not record preparation failure before execution"
        )
    if (
        "upgrade_database_blocked=0" not in source
        or '[[ "$lane" == "full" ]] && (( upgrade_database_blocked ))' not in source
        or 'record_skipped_lane "$lane" "upgrade database preparation failed; full lane is unavailable"'
        not in source
        or "upgrade_database_blocked=1" not in source[preparation_failure:]
    ):
        violations.append(
            "full lane is not skipped when upgrade database preparation fails"
        )
    if "classify_release_failure.py" not in source:
        violations.append("failed lanes are not classified from their logs")
    if (
        "database_for_lane()" not in source
        or "upgrade|full)" not in source
        or source.count('database_for_lane "$lane"') < 2
    ):
        violations.append(
            "upgrade and full lane evidence do not use the upgrade database"
        )
    if not classifier.is_file():
        violations.append("release failure classifier is missing")
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("Release baseline evidence contract failed:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Release baseline evidence contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
