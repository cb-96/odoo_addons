import importlib.util, json, sys, hashlib
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


known = load("known_release_failures", ROOT / "ci/check_known_release_failures.py")
finalize = load("finalize_release_evidence", ROOT / "ci/finalize_release_evidence.py")


def test_empty_known_failure_registry_is_valid(tmp_path):
    p = tmp_path / "known.json"
    p.write_text('{"schema_version": 1, "failures": []}')
    assert known.validate(p, date(2026, 9, 10)) == []


def test_expired_known_failure_is_rejected(tmp_path):
    p = tmp_path / "known.json"
    p.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "failures": [
                    {
                        "id": "example-failure",
                        "lane": "full",
                        "classification": "product_defect",
                        "owner": "Platform Team",
                        "issue_url": "https://github.com/example/repo/issues/1",
                        "test": "Example.test_failure",
                        "reason": "Temporary exception",
                        "expires_on": "2026-09-09",
                    }
                ],
            }
        )
    )
    assert any("expired" in e for e in known.validate(p, date(2026, 9, 10)))


def test_evidence_from_other_commit_is_incomplete(tmp_path):
    evidence = tmp_path / "evidence"
    logs = evidence / "logs"
    logs.mkdir(parents=True)
    log = logs / "static.log"
    log.write_text("ok\n")
    record = {
        "schema_version": 2,
        "lane": "static",
        "status": "passed",
        "commit": "old-commit",
        "exit_code": 0,
        "command": "validate",
        "started_at": "2026-09-10T00:00:00Z",
        "finished_at": "2026-09-10T00:00:01Z",
        "duration_seconds": 1,
        "log": {
            "path": str(log),
            "sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
            "size_bytes": log.stat().st_size,
        },
    }
    (evidence / "lane-static.json").write_text(json.dumps(record))
    summary = finalize.build_summary(evidence, ("static",), "new-commit")
    assert summary["commit_mismatches"] == ["static"]
    assert not summary["complete"]
