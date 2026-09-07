import argparse
import importlib.util
import json
import subprocess
from pathlib import Path

CAPTURE_PATH = Path(__file__).with_name("capture_release_evidence.py")
FINALIZE_PATH = Path(__file__).with_name("finalize_release_evidence.py")


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture = load(CAPTURE_PATH, "capture_release_evidence")
finalize = load(FINALIZE_PATH, "finalize_release_evidence")


def init_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "tracked.txt").write_text("fixture\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)


def args(tmp_path, **overrides):
    values = dict(
        lane="static",
        status="passed",
        command="scripts/ci/run_rc_validation.sh static",
        exit_code=0,
        started_at="2026-09-07T10:00:00+00:00",
        finished_at="2026-09-07T10:00:01+00:00",
        duration_seconds=1.0,
        database="test",
        backup=None,
        log=tmp_path / "static.log",
        failure_classification=None,
        skip_reason=None,
        output=tmp_path / "static.json",
    )
    values.update(overrides)
    values["log"].write_text("release evidence\n")
    return argparse.Namespace(**values)


def test_sha256(tmp_path):
    path = tmp_path / "backup.dump"
    path.write_bytes(b"release-evidence")
    assert capture.sha256(path) == (
        "86d2013e196c2988bd1058ee04da96a95ff8dc094d511295329b207e74eb88b6"
    )


def test_complete_evidence_records_log_and_environment(tmp_path):
    init_repo(tmp_path)
    evidence = capture.build_evidence(args(tmp_path), root=tmp_path)
    assert evidence["schema_version"] == 2
    assert evidence["status"] == "passed"
    assert evidence["log"]["size_bytes"] > 0
    assert evidence["log"]["sha256"]
    assert evidence["tools"]["git"].startswith("git version")


def test_failed_lane_requires_classification(tmp_path):
    init_repo(tmp_path)
    try:
        capture.build_evidence(
            args(tmp_path, status="failed", exit_code=1), root=tmp_path
        )
    except ValueError as exc:
        assert "failure-classification" in str(exc)
    else:
        raise AssertionError("unclassified failure was accepted")


def test_finalizer_rejects_missing_and_skipped_required_lanes(tmp_path):
    init_repo(tmp_path)
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    passed = capture.build_evidence(args(tmp_path), root=tmp_path)
    (evidence_dir / "lane-static.json").write_text(json.dumps(passed))
    summary = finalize.build_summary(
        evidence_dir,
        ("static", "full"),
        passed["commit"],
    )
    assert summary["status"] == "failed"
    assert summary["missing_lanes"] == ["full"]


def test_finalizer_accepts_complete_passing_set(tmp_path):
    init_repo(tmp_path)
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    for lane in ("static", "full"):
        lane_args = args(tmp_path, lane=lane, log=tmp_path / f"{lane}.log")
        evidence = capture.build_evidence(lane_args, root=tmp_path)
        (evidence_dir / f"lane-{lane}.json").write_text(json.dumps(evidence))
    commit = capture.run("git", "rev-parse", "HEAD", root=tmp_path)
    summary = finalize.build_summary(evidence_dir, ("static", "full"), commit)
    assert summary["status"] == "passed"
    assert summary["complete"] is True
