#!/usr/bin/env python3
"""Keep migration rehearsal tooling and documentation wired together."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "ci/release_invariants.json": ("schema_version", "counts", "zero_checks"),
    "ci/capture_migration_invariants.py": ("validate_contract", "run_sql", "count_modes"),
    "ci/compare_migration_invariants.py": ("force_exact", "differences"),
    "scripts/ci/run_migration_rehearsal.sh": (
        "restore_backup_drill.sh",
        "run_rc_validation.sh acceptance",
        "rollback-owner",
        "rollback-trigger",
        "invariant-comparison.json",
    ),
    "RELEASE_RUNBOOK.md": ("Migration rehearsal evidence", "run_migration_rehearsal.sh"),
    "docs/DELIVERY_ROADMAP.md": ("Release Candidate and Migration Evidence", "run_migration_rehearsal.sh"),
}


def main() -> int:
    errors = []
    for relative, tokens in REQUIRED.items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing {relative}")
            continue
        source = path.read_text(encoding="utf-8")
        for token in tokens:
            if token not in source:
                errors.append(f"{relative} missing {token!r}")
    if errors:
        print("Migration rehearsal contract failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Migration rehearsal contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
