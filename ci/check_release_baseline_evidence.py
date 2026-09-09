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
    if "sports-federation-release-baseline" not in source:
        violations.append("default release evidence is not outside the repository")
    if "Evidence directory must be outside the repository" not in source:
        violations.append("in-repository release evidence is not rejected")
    if "classify_release_failure.py" not in source:
        violations.append("failed lanes are not classified from their logs")
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
