#!/usr/bin/env python3
"""Combine automated release evidence and browser walkthrough evidence.

Inputs, all inside one private evidence directory:

* ``summary.json``  written by ``scripts/ci/run_release_baseline.sh``
* ``walkthrough/walkthrough.json`` written by the walkthrough agent
* ``human-acceptance.json`` (optional) novice-user session record

Writes ``end-to-end-summary.json`` and exits 0 only when the requested level is
met. Levels: ``technical`` (automated lanes + walkthrough) and ``release``
(technical + completed human acceptance).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ci" / "release_confidence" / "competition_lifecycle.json"
STEP_STATUSES = {"passed", "failed", "blocked"}
SEVERITIES = {"blocker", "major", "minor"}
CLASSIFICATIONS = {"product", "test", "environment"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def head_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def read_json(path: Path) -> tuple[dict | None, str | None]:
    if not path.is_file():
        return None, f"{path.name}: missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except ValueError as exc:
        return None, f"{path.name}: invalid JSON ({exc})"


def check_baseline(evidence_dir: Path, commit: str) -> list[str]:
    summary, error = read_json(evidence_dir / "summary.json")
    if error:
        return [error]
    issues = []
    if summary.get("commit") != commit:
        issues.append(
            f"summary.json: commit {summary.get('commit')} is not the candidate {commit}"
        )
    if not summary.get("complete"):
        issues.append("summary.json: evidence set is incomplete")
    for key in (
        "failed_lanes",
        "missing_lanes",
        "skipped_lanes",
        "invalid_records",
        "commit_mismatches",
    ):
        if summary.get(key):
            issues.append(f"summary.json: {key} = {summary[key]}")
    lanes = {lane.get("lane") for lane in summary.get("lanes", [])}
    if "lifecycle" not in lanes:
        issues.append("summary.json: the lifecycle lane was not recorded")
    return issues


def check_walkthrough(
    evidence_dir: Path, commit: str, contract: dict
) -> tuple[list[str], list[dict]]:
    walk_dir = evidence_dir / "walkthrough"
    data, error = read_json(walk_dir / "walkthrough.json")
    if error:
        return [error], []
    issues: list[str] = []
    if data.get("schema_version") != 1:
        issues.append("walkthrough.json: schema_version must be 1")
    if data.get("commit") != commit:
        issues.append(
            f"walkthrough.json: commit {data.get('commit')} is not the candidate {commit}"
        )
    steps = {
        step.get("id"): step for step in data.get("steps", []) if isinstance(step, dict)
    }
    for required in contract["walkthrough"]["required_steps"]:
        step = steps.get(required["id"])
        if not step:
            issues.append(f"walkthrough step {required['id']}: missing")
            continue
        status = step.get("status")
        if status not in STEP_STATUSES:
            issues.append(
                f"walkthrough step {required['id']}: invalid status {status!r}"
            )
        elif status != "passed":
            issues.append(f"walkthrough step {required['id']}: {status}")
        if step.get("viewport") != required["viewport"]:
            issues.append(
                f"walkthrough step {required['id']}: viewport {step.get('viewport')!r}, expected {required['viewport']!r}"
            )
        if not str(step.get("actor_login") or "").strip():
            issues.append(f"walkthrough step {required['id']}: actor_login missing")
        shots = step.get("screenshots") or []
        if not shots:
            issues.append(f"walkthrough step {required['id']}: no screenshot")
        for shot in shots:
            path = (walk_dir / str(shot.get("path", ""))).resolve()
            if walk_dir.resolve() not in path.parents or not path.is_file():
                issues.append(
                    f"walkthrough step {required['id']}: screenshot {shot.get('path')} missing"
                )
            elif sha256(path) != shot.get("sha256"):
                issues.append(
                    f"walkthrough step {required['id']}: screenshot {shot.get('path')} checksum mismatch"
                )
    defects = data.get("defects", [])
    for defect in defects:
        if (
            defect.get("severity") not in SEVERITIES
            or defect.get("classification") not in CLASSIFICATIONS
        ):
            issues.append(
                f"defect {defect.get('id')}: needs a valid severity and classification"
            )
        if defect.get("severity") == "blocker" and defect.get("status") != "resolved":
            issues.append(f"defect {defect.get('id')}: unresolved blocker")
    return issues, defects


def check_human(evidence_dir: Path, commit: str) -> tuple[str, list[str]]:
    data, error = read_json(evidence_dir / "human-acceptance.json")
    if error:
        return "missing", [error]
    issues = []
    if data.get("commit") != commit:
        issues.append("human-acceptance.json: recorded for another commit")
    sessions = data.get("sessions", [])
    if not isinstance(sessions, list) or any(not isinstance(session, dict) for session in sessions):
        return "incomplete", ["human-acceptance.json: sessions must be a list of objects"]
    roles = {session.get("role") for session in sessions if session.get("completed") is True}
    for role in ("club_representative", "organiser", "court_operator"):
        count = sum(1 for s in sessions if s.get("role") == role and s.get("completed") is True)
        if count < 5:
            issues.append(f"human-acceptance.json: {count} {role} completed sessions, need at least 5")
    if not roles:
        issues.append("human-acceptance.json: no completed sessions")
    if data.get("critical_incidents"):
        issues.append("human-acceptance.json: critical incidents recorded")
    return ("completed" if not issues else "incomplete"), issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--level", choices=("technical", "release"), default="release")
    parser.add_argument("--commit", default=None)
    args = parser.parse_args(argv)
    evidence_dir = args.evidence_dir.resolve()
    commit = args.commit or head_commit()
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    baseline_issues = check_baseline(evidence_dir, commit)
    walkthrough_issues, defects = check_walkthrough(evidence_dir, commit, contract)
    human_status, human_issues = check_human(evidence_dir, commit)
    technical_ok = not baseline_issues and not walkthrough_issues
    release_ok = technical_ok and human_status == "completed"
    verdict = (
        "release-qualified"
        if release_ok
        else ("technically-qualified" if technical_ok else "not-qualified")
    )
    summary = {
        "schema_version": 1,
        "commit": commit,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "automated": {"ok": not baseline_issues, "issues": baseline_issues},
        "walkthrough": {
            "ok": not walkthrough_issues,
            "issues": walkthrough_issues,
            "defects": defects,
        },
        "human_acceptance": {"status": human_status, "issues": human_issues},
    }
    (evidence_dir / "end-to-end-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"[e2e] Verdict for {commit}: {verdict}")
    for section in ("automated", "walkthrough"):
        for issue in summary[section]["issues"]:
            print(f"[e2e] {section}: {issue}", file=sys.stderr)
    for issue in human_issues:
        print(f"[e2e] human acceptance: {issue}", file=sys.stderr)
    if args.level == "technical":
        return 0 if technical_ok else 1
    return 0 if release_ok else 1


if __name__ == "__main__":
    sys.exit(main())
