"""Release orchestration regressions; backends are mocked, not qualified here."""

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch
import unittest

from ci import run_release as runner


class TestReleaseRunner(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.evidence = Path(self.temp.name) / "evidence"
        self.backup = Path(self.temp.name) / "backup"
        self.backup.mkdir()
        self.calls = []
        self.env = {"TMPDIR": self.temp.name}

    def execute(self, argv, env, root):
        self.calls.append(([str(arg) for arg in argv], dict(env), root))
        if argv[1] == "scripts/ci/run_release_baseline.sh":
            logs = Path(env["RELEASE_BASELINE_EVIDENCE_DIR"]) / "logs"
            logs.mkdir(parents=True, exist_ok=True)
            (logs / "focus.log").write_text("browser evidence")

    def run_profile(self, *argv, execute=None):
        args = runner.parser().parse_args(argv)
        with redirect_stdout(StringIO()):
            runner.run(
                args,
                env=self.env,
                execute=execute or self.execute,
                get_revision=lambda root: "candidate-sha",
                root=self.root,
            )

    def names(self):
        return [call[0][1] for call in self.calls]

    def test_candidate_runs_baseline_once_without_claiming_qualification(self):
        output = StringIO()
        with redirect_stdout(output):
            runner.run(
                runner.parser().parse_args(["candidate"]),
                env=self.env,
                execute=self.execute,
                get_revision=lambda root: "sha",
                root=self.root,
            )
        self.assertEqual(
            self.names(),
            [
                "ci/check_rc_product_readiness.py",
                "ci/check_rc_usability.py",
                "scripts/ci/run_release_baseline.sh",
            ],
        )
        self.assertIn("NOT performed", output.getvalue())

    def test_readiness_validates_commit_and_browser_logs(self):
        self.run_profile("readiness", "--evidence-dir", str(self.evidence))
        self.assertEqual(
            self.names(),
            [
                "ci/check_always_invisible_fields.py",
                "ci/check_reliability_contract.py",
                "scripts/ci/run_release_baseline.sh",
                "ci/check_release_evidence.py",
                "ci/check_browser_release_log.py",
            ],
        )
        self.assertIn("--require-passing", self.calls[3][0])
        self.assertIn("candidate-sha", self.calls[3][0])
        self.assertEqual(self.calls[4][0][-1], str(self.evidence / "logs/focus.log"))

    def test_qualification_requires_inputs_before_any_command(self):
        with self.assertRaises(ValueError):
            self.run_profile("qualification")
        self.assertEqual(self.calls, [])

    def test_incomplete_candidate_migration_is_rejected_early(self):
        with self.assertRaises(ValueError):
            self.run_profile("candidate", "--backup-dir", str(self.backup))
        self.assertEqual(self.calls, [])

    def test_missing_backup_is_rejected(self):
        with self.assertRaises(ValueError):
            self.run_profile(
                "qualification",
                "--backup-dir",
                str(self.backup / "missing"),
                "--rollback-owner",
                "owner",
                "--rollback-trigger",
                "trigger",
            )
        self.assertEqual(self.calls, [])

    def test_qualification_preserves_all_gates_and_shared_evidence(self):
        self.run_profile(
            "qualification",
            "--backup-dir",
            str(self.backup),
            "--rollback-owner",
            "owner",
            "--rollback-trigger",
            "trigger",
            "--evidence-dir",
            str(self.evidence),
        )
        self.assertEqual(self.names().count("scripts/ci/run_release_baseline.sh"), 1)
        self.assertEqual(
            self.names()[-2:],
            ["scripts/ci/run_migration_rehearsal.sh", "ci/check_release_signoff.py"],
        )
        self.assertIn("--yes", self.calls[-2][0])
        self.assertIn(str(self.evidence / "summary.json"), self.calls[-1][0])
        self.assertTrue(
            all(
                call[1]["RELEASE_BASELINE_EVIDENCE_DIR"] == str(self.evidence)
                for call in self.calls
            )
        )

    def test_environment_qualification_inputs_remain_supported(self):
        self.env.update(
            RELEASE_BACKUP_DIR=str(self.backup),
            ROLLBACK_OWNER="owner",
            ROLLBACK_TRIGGER="trigger",
        )
        self.run_profile("qualification")
        self.assertEqual(self.names()[-1], "ci/check_release_signoff.py")

    def test_failure_stops_before_migration_or_signoff(self):
        def fail(argv, env, root):
            self.execute(argv, env, root)
            if argv[1] == "ci/check_release_evidence.py":
                raise subprocess.CalledProcessError(7, argv)

        with self.assertRaises(subprocess.CalledProcessError):
            self.run_profile(
                "qualification",
                "--backup-dir",
                str(self.backup),
                "--rollback-owner",
                "owner",
                "--rollback-trigger",
                "trigger",
                execute=fail,
            )
        self.assertNotIn("scripts/ci/run_migration_rehearsal.sh", self.names())
        self.assertNotIn("ci/check_release_signoff.py", self.names())

    def test_no_browser_logs_is_failure(self):
        def no_logs(argv, env, root):
            self.calls.append(([str(arg) for arg in argv], dict(env), root))

        with self.assertRaisesRegex(ValueError, "browser-capable"):
            self.run_profile("readiness", execute=no_logs)

    def test_repository_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            self.run_profile(
                "candidate", "--evidence-dir", str(self.root / "artifacts")
            )
        self.assertEqual(self.calls, [])

    def test_symlink_into_repository_is_rejected(self):
        link = Path(self.temp.name) / "evidence-link"
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            runner.external(link, self.root)

    def test_rc_cleanup_and_retention_pass_through(self):
        self.env["RC_COMPOSE_RETAIN"] = "1"
        self.run_profile("rc", "--lane", "cleanup")
        self.assertEqual(
            self.calls[0][0], ["bash", "scripts/ci/run_rc_validation.sh", "cleanup"]
        )
        self.assertEqual(self.calls[0][1]["RC_COMPOSE_RETAIN"], "1")

    def test_specialized_backend_arguments_are_not_shell_interpolated(self):
        self.run_profile(
            "migration",
            "--",
            "--backup-dir",
            "/backup with spaces",
            "--rollback-owner",
            "a;b",
        )
        self.assertEqual(
            self.calls[0][0][-4:],
            ["--backup-dir", "/backup with spaces", "--rollback-owner", "a;b"],
        )

    def test_walkthrough_and_confidence_use_existing_backends(self):
        self.run_profile("walkthrough", "--", "verify")
        self.run_profile("confidence", "--", "verify", "--evidence-dir", "/evidence")
        self.assertEqual(
            self.names(),
            ["scripts/ci/run_end_to_end_release.sh", "ci/release_confidence.py"],
        )

    def test_all_rc_lanes_delegate_without_reordering(self):
        for lane in runner.RC_LANES:
            self.run_profile("rc", "--lane", lane)
            self.assertEqual(self.calls[-1][0][-1], lane)

    def test_migration_failure_prevents_signoff(self):
        def fail(argv, env, root):
            self.execute(argv, env, root)
            if argv[1] == "scripts/ci/run_migration_rehearsal.sh":
                raise subprocess.CalledProcessError(6, argv)

        with self.assertRaises(subprocess.CalledProcessError):
            self.run_profile(
                "qualification",
                "--backup-dir",
                str(self.backup),
                "--rollback-owner",
                "owner",
                "--rollback-trigger",
                "trigger",
                execute=fail,
            )
        self.assertNotIn("ci/check_release_signoff.py", self.names())

    def test_legacy_wrappers_expose_profile_help_without_running_backends(self):
        for name in ("candidate", "readiness", "qualification"):
            script = runner.ROOT / "scripts/ci" / ("run_release_" + name + ".sh")
            result = subprocess.run(
                ["bash", str(script), "--help"],
                cwd=self.temp.name,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(name, result.stdout)
            self.assertIn("--evidence-dir", result.stdout)

    def test_main_preserves_backend_failure_code(self):
        with patch.object(
            runner, "run", side_effect=subprocess.CalledProcessError(9, ["backend"])
        ):
            self.assertEqual(runner.main(["rc", "--lane", "static"]), 9)

    def test_main_reports_invalid_inputs(self):
        with patch.object(
            runner, "run", side_effect=ValueError("missing backup")
        ), redirect_stderr(StringIO()):
            self.assertEqual(runner.main(["qualification"]), 2)

    def test_invoke_uses_cwd_environment_and_check(self):
        with patch.object(subprocess, "run") as call, redirect_stdout(StringIO()):
            runner.invoke(
                ["bash", "backend", "argument with spaces"], self.env, self.root
            )
        call.assert_called_once_with(
            ["bash", "backend", "argument with spaces"],
            cwd=self.root,
            env=self.env,
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
