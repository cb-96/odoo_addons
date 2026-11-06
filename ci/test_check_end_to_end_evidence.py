#!/usr/bin/env python3
"""Tests for ci/check_end_to_end_evidence.py."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_end_to_end_evidence as e2e  # noqa: E402

COMMIT = "a" * 40
CONTRACT = json.loads(e2e.CONTRACT.read_text(encoding="utf-8"))


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def evidence(walk_status: str = "passed", human: bool = False) -> Path:
    root = Path(tempfile.mkdtemp())
    write(root / "summary.json", {
        "commit": COMMIT, "complete": True, "failed_lanes": [], "missing_lanes": [],
        "skipped_lanes": [], "invalid_records": [], "commit_mismatches": [],
        "lanes": [{"lane": "lifecycle"}, {"lane": "full"}],
    })
    shot = root / "walkthrough" / "screenshots" / "shot.png"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"png")
    digest = hashlib.sha256(b"png").hexdigest()
    steps = [
        {"id": step["id"], "status": walk_status, "viewport": step["viewport"],
         "actor_login": "user@walkthrough.invalid",
         "screenshots": [{"path": "screenshots/shot.png", "sha256": digest}]}
        for step in CONTRACT["walkthrough"]["required_steps"]
    ]
    write(root / "walkthrough" / "walkthrough.json",
          {"schema_version": 1, "commit": COMMIT, "steps": steps, "defects": []})
    if human:
        sessions = [{"role": role, "completed": True}
                    for role in ("club_representative", "organiser", "court_operator")
                    for _ in range(5)]
        write(root / "human-acceptance.json",
              {"commit": COMMIT, "sessions": sessions, "critical_incidents": []})
    return root


def run(root: Path, level: str) -> tuple[int, dict]:
    code = e2e.main(["--evidence-dir", str(root), "--commit", COMMIT, "--level", level])
    return code, json.loads((root / "end-to-end-summary.json").read_text(encoding="utf-8"))


class EvidenceTests(unittest.TestCase):
    def test_technical_pass_without_human_sessions(self):
        code, summary = run(evidence(), "technical")
        self.assertEqual(code, 0)
        self.assertEqual(summary["verdict"], "technically-qualified")

    def test_release_level_requires_human_sessions(self):
        self.assertEqual(run(evidence(), "release")[0], 1)
        code, summary = run(evidence(human=True), "release")
        self.assertEqual(code, 0)
        self.assertEqual(summary["verdict"], "release-qualified")

    def test_failed_step_is_not_qualified(self):
        code, summary = run(evidence("failed"), "technical")
        self.assertEqual(code, 1)
        self.assertEqual(summary["verdict"], "not-qualified")

    def test_tampered_screenshot_is_rejected(self):
        root = evidence()
        (root / "walkthrough" / "screenshots" / "shot.png").write_bytes(b"other")
        self.assertEqual(run(root, "technical")[0], 1)

    def test_other_commit_and_missing_lifecycle_lane_are_rejected(self):
        root = evidence()
        summary = json.loads((root / "summary.json").read_text())
        summary["commit"] = "b" * 40
        summary["lanes"] = [{"lane": "full"}]
        write(root / "summary.json", summary)
        code, result = run(root, "technical")
        self.assertEqual(code, 1)
        self.assertTrue(any("lifecycle" in issue for issue in result["automated"]["issues"]))

    def test_unresolved_blocker_defect_is_rejected(self):
        root = evidence()
        path = root / "walkthrough" / "walkthrough.json"
        data = json.loads(path.read_text())
        data["defects"] = [{"id": "D1", "severity": "blocker", "classification": "product", "status": "open"}]
        write(path, data)
        self.assertEqual(run(root, "technical")[0], 1)

    def test_screenshot_outside_walkthrough_dir_is_rejected(self):
        root = evidence()
        path = root / "walkthrough" / "walkthrough.json"
        data = json.loads(path.read_text())
        data["steps"][0]["screenshots"][0]["path"] = "../summary.json"
        write(path, data)
        self.assertEqual(run(root, "technical")[0], 1)


if __name__ == "__main__":
    unittest.main()
