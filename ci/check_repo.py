#!/usr/bin/env python3
"""Single repository-check entry point backed by existing focused checks."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKS = {
    "integrity": (
        "ci/check_addon_integrity.py",
        "ci/check_access_csv_integrity.py",
        "ci/check_application_entrypoint.py",
        "ci/check_module_dependency_drift.py",
        "ci/check_module_owners.py",
    ),
    "security": (
        "ci/check_audit_acl_integrity.py",
        "ci/check_http_route_ownership.py",
        "ci/check_portal_sudo_guard.py",
        "ci/check_privileged_command_contracts.py",
        "ci/check_privileged_mutation_boundaries.py",
    ),
    "workflows": (
        "ci/check_competition_pipeline_contract.py",
        "ci/check_competition_ui_workflow.py",
        "ci/check_fixture_ownership_contract.py",
        "ci/check_matchday_transition_contract.py",
        "ci/check_publication_integrity_contract.py",
        "ci/check_result_transition_contract.py",
        "ci/check_workflow_state_contracts.py",
    ),
    "compatibility": (
        "ci/check_always_invisible_fields.py",
        "ci/check_legacy_engine_removed.py",
        "ci/check_markdown_links.py",
        "ci/check_migration_review.py",
        "ci/check_test_discovery.py",
    ),
    "release": (
        "ci/check_known_release_failures.py",
        "ci/check_rc_product_readiness.py",
        "ci/check_rc_test_scope.py",
        "ci/check_release_focus_contract.py",
        "ci/check_reliability_contract.py",
    ),
}


@dataclass(frozen=True)
class Result:
    check: str
    status: str
    duration_seconds: float
    returncode: int


def run_check(relative_path: str) -> Result:
    path = ROOT / relative_path
    if not path.is_file():
        return Result(relative_path, "missing", 0.0, 2)
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, str(path)], cwd=ROOT, check=False
    )
    duration = round(time.monotonic() - started, 3)
    status = "passed" if completed.returncode == 0 else "failed"
    return Result(relative_path, status, duration, completed.returncode)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("area", choices=(*CHECKS, "all"))
    parser.add_argument("--json", type=Path, dest="json_path")
    parser.add_argument("--keep-going", action="store_true")
    args = parser.parse_args(argv)

    areas = CHECKS if args.area == "all" else {args.area: CHECKS[args.area]}
    results = []
    for area, checks in areas.items():
        print(f"\n[{area}]", flush=True)
        for check in checks:
            result = run_check(check)
            results.append(result)
            print(
                f"  {result.status:7} {result.check} "
                f"({result.duration_seconds:.3f}s)",
                flush=True,
            )
            if result.returncode and not args.keep_going:
                break
        if results[-1].returncode and not args.keep_going:
            break

    payload = {
        "area": args.area,
        "status": "passed" if all(not item.returncode for item in results) else "failed",
        "results": [asdict(item) for item in results],
    }
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(json.dumps(payload, indent=2) + "\n")
    return 0 if payload["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
