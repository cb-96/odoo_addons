#!/usr/bin/env python3
"""Verify that Package 7 release-qualification controls remain wired."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
rc_script = (ROOT / "scripts/ci/run_rc_validation.sh").read_text(encoding="utf-8")
workflow = (ROOT / ".github/workflows/release-candidate.yml").read_text(
    encoding="utf-8"
)
acceptance = (ROOT / "docs/release/COMPETITION_CUTOVER_ACCEPTANCE.md").read_text(
    encoding="utf-8"
)
next_phases = (ROOT / "docs/release/POST_CUTOVER_PHASES.md").read_text(encoding="utf-8")

checks = {
    "RC upgrade lane": "upgrade)" in rc_script,
    "RC public lane": "public)" in rc_script,
    "upgrade database isolation": "UPGRADE_DB_NAME" in rc_script,
    "upgrade precondition": "assert_modules_installed" in rc_script,
    "workflow upgrade execution": "run_rc_validation.sh upgrade" in workflow,
    "workflow public execution": "run_rc_validation.sh public" in workflow,
    "acceptance exact commit evidence": "Candidate commit SHA" in acceptance,
    "acceptance route cutover evidence": "/competitions" in acceptance
    and "/tournaments" in acceptance,
    "acceptance full lifecycle": all(
        token in acceptance
        for token in (
            "Registration",
            "Format and fixtures",
            "Calendar and scheduling",
            "Approval and publication",
            "Match-day operations",
            "Results and standings",
        )
    ),
    "post-cutover decision gate": "Decision gate" in next_phases,
}
failed = [name for name, passed in checks.items() if not passed]
if failed:
    print(
        "Package 7 release qualification contract failed: " + ", ".join(failed),
        file=sys.stderr,
    )
    raise SystemExit(1)
print("Package 7 release qualification contract passed.")
