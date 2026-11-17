"""Negative evidence regressions with test fixtures, not real release evidence."""

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from ci import migration_evidence as migration
from ci.check_release_signoff import validate
from ci.check_end_to_end_evidence import check_human
from ci import run_release

COMMIT = "a" * 40


class TestMigrationEvidence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        contract = migration.read_object(migration.CONTRACT)
        self.snapshot = {
            "schema_version": 1,
            "counts": {key: 10 for key in contract["counts"]},
            "zero_checks": {key: 0 for key in contract["zero_checks"]},
            "count_modes": {
                key: contract.get("count_modes", {}).get(key, "exact")
                for key in contract["counts"]
            },
        }
        for name in ("before-upgrade.json", "after-upgrade.json", "rollback.json"):
            self.write(name, self.snapshot)
        self.write(
            "invariant-comparison.json",
            {"schema_version": 1, "status": "passed", "differences": []},
        )
        for name in ("restore-before-upgrade.txt", "restore-rollback.txt"):
            (self.root / name).write_text("filestore_restored=yes\n")
        for name, lane, log_name in (
            ("upgrade.json", "migration-upgrade", "upgrade.log"),
            (
                "operator-acceptance.json",
                "role-separated-acceptance",
                "operator-acceptance.log",
            ),
        ):
            log = self.root / log_name
            log.write_text("isolated test fixture, not an executed runtime log\n")
            self.write(
                name,
                {
                    "schema_version": 2,
                    "commit": COMMIT,
                    "lane": lane,
                    "status": "passed",
                    "exit_code": 0,
                    "log": {"sha256": migration.digest(log)},
                },
            )
        self.backup = self.root / "test-fixture.dump"
        self.backup.write_bytes(b"test fixture, not a database backup")

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value))

    def seal(self):
        return migration.seal(self.root, COMMIT, self.backup, "owner", "trigger")

    def test_complete_bundle_seals_and_verifies(self):
        manifest = self.seal()
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(migration.validate_bundle(self.root, COMMIT), [])

    def test_wrong_commit_is_rejected(self):
        self.seal()
        self.assertTrue(
            any(
                "candidate commit" in error
                for error in migration.validate_bundle(self.root, "b" * 40)
            )
        )

    def test_changed_artifact_is_rejected(self):
        self.seal()
        (self.root / "restore-rollback.txt").write_text(
            "filestore_restored=yes\nchanged\n"
        )
        self.assertTrue(
            any(
                "checksum" in error
                for error in migration.validate_bundle(self.root, COMMIT)
            )
        )

    def test_missing_artifact_cannot_be_sealed(self):
        (self.root / "rollback.json").unlink()
        with self.assertRaises(ValueError):
            self.seal()
        self.assertFalse((self.root / "manifest.json").exists())

    def test_skipped_filestore_is_rejected(self):
        (self.root / "restore-rollback.txt").write_text("filestore_restored=no\n")
        with self.assertRaisesRegex(ValueError, "filestore"):
            self.seal()

    def test_false_passing_comparison_is_recomputed(self):
        changed = deepcopy(self.snapshot)
        changed["counts"]["clubs"] += 1
        self.write("after-upgrade.json", changed)
        with self.assertRaisesRegex(ValueError, "Recomputed"):
            self.seal()

    def test_rollback_must_be_exact_even_for_minimum_counts(self):
        changed = deepcopy(self.snapshot)
        changed["counts"]["attachments"] += 1
        self.write("rollback.json", changed)
        with self.assertRaisesRegex(ValueError, "Recomputed"):
            self.seal()

    def test_incomplete_invariant_snapshot_is_rejected(self):
        changed = deepcopy(self.snapshot)
        changed["zero_checks"].pop(next(iter(changed["zero_checks"])))
        self.write("after-upgrade.json", changed)
        with self.assertRaisesRegex(ValueError, "cover the invariant contract"):
            self.seal()

    def test_changed_count_modes_are_rejected(self):
        changed = deepcopy(self.snapshot)
        changed["count_modes"]["clubs"] = "minimum"
        self.write("before-upgrade.json", changed)
        with self.assertRaisesRegex(ValueError, "count modes"):
            self.seal()

    def test_retired_engine_blocker_is_not_cleared_by_status(self):
        changed = deepcopy(self.snapshot)
        changed["zero_checks"]["retired_competition_engine_not_upgradeable"] = 1
        self.write("after-upgrade.json", changed)
        with self.assertRaisesRegex(ValueError, "Recomputed"):
            self.seal()

    def test_symlink_artifact_cannot_escape_bundle(self):
        with tempfile.TemporaryDirectory() as other:
            external = Path(other) / "rollback.json"
            external.write_text(json.dumps(self.snapshot))
            (self.root / "rollback.json").unlink()
            (self.root / "rollback.json").symlink_to(external)
            with self.assertRaisesRegex(ValueError, "escaped"):
                self.seal()

    def test_old_manifest_is_not_grandfathered(self):
        manifest = self.seal()
        manifest["schema_version"] = 1
        self.write("manifest.json", manifest)
        self.assertTrue(
            any(
                "schema 2" in error
                for error in migration.validate_bundle(self.root, COMMIT)
            )
        )

    def test_malformed_json_is_rejected(self):
        (self.root / "rollback.json").write_text("[]")
        with self.assertRaises(ValueError):
            self.seal()

    def test_wrong_runtime_commit_is_rejected(self):
        record = migration.read_object(self.root / "upgrade.json")
        record["commit"] = "b" * 40
        self.write("upgrade.json", record)
        with self.assertRaisesRegex(ValueError, "another candidate"):
            self.seal()

    def test_failed_runtime_lane_is_rejected(self):
        record = migration.read_object(self.root / "upgrade.json")
        record["exit_code"] = 1
        self.write("upgrade.json", record)
        with self.assertRaisesRegex(ValueError, "not passing"):
            self.seal()

    def test_overwritten_runtime_log_is_rejected(self):
        (self.root / "upgrade.log").write_text("overwritten")
        with self.assertRaisesRegex(ValueError, "not bound"):
            self.seal()

    def test_short_commit_cannot_be_sealed(self):
        with self.assertRaises(ValueError):
            migration.seal(self.root, "abc", self.backup, "owner", "trigger")


class TestReleaseSignoff(unittest.TestCase):
    def test_migration_commit_is_required(self):
        baseline = {"commit": COMMIT, "status": "passed", "complete": True}
        manifest = {
            "status": "passed",
            "rollback_owner": "owner",
            "rollback_trigger": "trigger",
            "backup": {"sha256": "a" * 64},
        }
        self.assertTrue(
            any(
                "migration evidence belongs" in error
                for error in validate(baseline, manifest, COMMIT)
            )
        )
        manifest["commit"] = COMMIT
        self.assertEqual(validate(baseline, manifest, COMMIT), [])

    def test_missing_lanes_and_truthy_complete_do_not_pass(self):
        baseline = {
            "commit": COMMIT,
            "status": "passed",
            "complete": "yes",
            "missing_lanes": ["full"],
        }
        manifest = {
            "commit": COMMIT,
            "status": "passed",
            "rollback_owner": "owner",
            "rollback_trigger": "trigger",
            "backup": {"sha256": "a" * 64},
        }
        errors = validate(baseline, manifest, COMMIT)
        self.assertTrue(any("complete" in error for error in errors))
        self.assertTrue(any("missing_lanes" in error for error in errors))


class TestHumanAcceptance(unittest.TestCase):
    def check(self, sessions, **extra):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "human-acceptance.json").write_text(
                json.dumps({"commit": COMMIT, "sessions": sessions, **extra})
            )
            return check_human(root, COMMIT)

    def sessions(self):
        return [
            {"role": role, "completed": True}
            for role in ("club_representative", "organiser", "court_operator")
            for _ in range(5)
        ]

    def test_completed_sessions_for_each_role_pass(self):
        self.assertEqual(self.check(self.sessions()), ("completed", []))

    def test_unfinished_sessions_do_not_count(self):
        sessions = self.sessions()
        for session in sessions:
            if session["role"] == "organiser":
                session["completed"] = False
        status, errors = self.check(sessions)
        self.assertEqual(status, "incomplete")
        self.assertTrue(
            any("0 organiser completed sessions" in error for error in errors)
        )

    def test_truthy_string_is_not_completed(self):
        sessions = self.sessions()
        for session in sessions:
            session["completed"] = "yes"
        self.assertEqual(self.check(sessions)[0], "incomplete")

    def test_malformed_sessions_are_rejected(self):
        self.assertEqual(self.check([None])[0], "incomplete")

    def test_critical_incidents_block_acceptance(self):
        self.assertEqual(
            self.check(self.sessions(), critical_incidents=["unresolved"])[0],
            "incomplete",
        )


class TestCompleteProfile(unittest.TestCase):
    def test_both_verifiers_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            evidence = Path(directory) / "evidence"
            calls = []
            args = run_release.parser().parse_args(
                ["verify-complete", "--evidence-dir", str(evidence)]
            )
            with redirect_stdout(StringIO()):
                run_release.run(
                    args,
                    env={},
                    root=root,
                    get_revision=lambda root: COMMIT,
                    execute=lambda argv, env, root: calls.append(
                        [str(value) for value in argv]
                    ),
                )
            self.assertEqual(
                [call[1] for call in calls],
                ["ci/release_confidence.py", "ci/check_end_to_end_evidence.py"],
            )
            self.assertIn("release", calls[1])
            self.assertIn(COMMIT, calls[1])

    def test_failed_confidence_prevents_usability_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            args = run_release.parser().parse_args(
                ["verify-complete", "--evidence-dir", str(Path(directory) / "evidence")]
            )
            calls = []

            def fail(argv, env, root):
                calls.append(argv)
                raise subprocess.CalledProcessError(1, argv)

            with self.assertRaises(subprocess.CalledProcessError):
                run_release.run(
                    args,
                    env={},
                    root=root,
                    get_revision=lambda root: COMMIT,
                    execute=fail,
                )
            self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
