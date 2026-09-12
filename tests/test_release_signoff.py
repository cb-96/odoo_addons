import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "signoff", ROOT / "ci/check_release_signoff.py"
)
signoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(signoff)


def passing_baseline():
    return {
        "commit": "abc",
        "status": "passed",
        "complete": True,
        "failed_lanes": [],
        "skipped_lanes": [],
        "commit_mismatches": [],
        "invalid_records": [],
    }


def passing_migration():
    return {
        "status": "passed",
        "rollback_owner": "Release owner",
        "rollback_trigger": "Invariant failure",
        "backup": {"sha256": "deadbeef"},
    }


def test_complete_evidence_passes():
    assert signoff.validate(passing_baseline(), passing_migration(), "abc") == []


def test_commit_mismatch_is_rejected():
    assert "baseline evidence belongs to another commit" in signoff.validate(
        passing_baseline(), passing_migration(), "def"
    )


def test_missing_rollback_governance_is_rejected():
    migration = passing_migration()
    migration["rollback_owner"] = ""
    assert "migration evidence has no rollback owner" in signoff.validate(
        passing_baseline(), migration, "abc"
    )
