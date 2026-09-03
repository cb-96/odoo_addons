import importlib.util
import json
from pathlib import Path


def load_script(name):
    path = Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture = load_script("capture_migration_invariants.py")
compare = load_script("compare_migration_invariants.py")


def test_contract_is_valid():
    contract = json.loads(
        Path(__file__).with_name("release_invariants.json").read_text()
    )
    capture.validate_contract(contract)


def test_comparison_accepts_preserved_counts_and_clean_integrity():
    before = {
        "counts": {"clubs": 3},
        "count_modes": {"clubs": "exact"},
        "zero_checks": {"orphans": 0},
    }
    after = {"counts": {"clubs": 3}, "zero_checks": {"orphans": 0}}
    assert compare.compare(before, after, "after") == []


def test_comparison_reports_count_and_integrity_drift():
    before = {
        "counts": {"clubs": 3},
        "count_modes": {"clubs": "exact"},
        "zero_checks": {"orphans": 0},
    }
    after = {"counts": {"clubs": 2}, "zero_checks": {"orphans": 1}}
    differences = compare.compare(before, after, "after")
    assert {item["kind"] for item in differences} == {"count", "integrity"}


def test_minimum_count_mode_allows_growth_but_not_loss():
    before = {
        "counts": {"attachments": 3},
        "count_modes": {"attachments": "minimum"},
        "zero_checks": {},
    }
    assert (
        compare.compare(
            before, {"counts": {"attachments": 4}, "zero_checks": {}}, "after"
        )
        == []
    )
    assert compare.compare(
        before, {"counts": {"attachments": 2}, "zero_checks": {}}, "after"
    )
    assert compare.compare(
        before,
        {"counts": {"attachments": 4}, "zero_checks": {}},
        "rollback",
        force_exact=True,
    )
