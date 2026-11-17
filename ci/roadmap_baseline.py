#!/usr/bin/env python3
"""Create a non-aspirational baseline before roadmap targets are selected.

Repository facts are measured here. Human journey and restored-database measures
remain explicit ``null`` values until a named evidence run supplies them; the
script never turns missing runtime evidence into a pass.
"""

import argparse
import json
import pathlib
import subprocess
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    args = parser.parse_args()
    python_tests = list(ROOT.glob("sports_federation_*/tests/test_*.py"))
    browser_tests = list(ROOT.glob("sports_federation_*/static/tests/**/*.js"))
    result = {
        "schema": "sports-federation-roadmap-baseline-v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": args.source_commit,
        "working_patch_head": git("rev-parse", "HEAD"),
        "worktree_clean": not bool(git("status", "--porcelain")),
        "repository": {
            "addons": len(list(ROOT.glob("sports_federation_*/__manifest__.py"))),
            "odoo_test_files": len(python_tests),
            "browser_test_files": len(browser_tests),
            "pure_capacity_tests": 4,
        },
        "qualification": {
            "full_ci_for_source_commit": None,
            "isolated_module_upgrade_for_source_commit": None,
            "restored_database_rehearsal_for_source_commit": None,
            "browser_walkthrough_for_source_commit": None,
            "note": "Populate only from evidence whose recorded commit equals source_commit.",
        },
        "journey_measures": {
            "completion_without_assistance": None,
            "minutes_to_prepare_and_publish_gameday": None,
            "unresolved_staffing_before_open": None,
            "unresolved_eligibility_before_open": None,
            "stale_acceptances_after_changes": None,
            "duplicate_duties": None,
            "duplicate_result_submissions": None,
            "offline_recovery_success_rate": None,
            "open_exceptions_at_season_close": None,
            "note": "Collect with realistic data before assigning numerical targets.",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(args.output)


if __name__ == "__main__":
    main()
