#!/usr/bin/env python3
"""Release profile orchestration; specialized backends retain their evidence gates.

This runner does not infer release readiness from a subprocess exit alone.
Readiness/qualification invoke the existing evidence validators explicitly.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RC_LANES = (
    "preflight", "static", "prepare", "install", "prepare-upgrade", "upgrade",
    "core", "portal", "public", "performance", "acceptance", "focus",
    "lifecycle", "full", "upstream", "cleanup", "all",
)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    profiles = result.add_subparsers(dest="profile", required=True)
    for name in ("candidate", "readiness", "qualification"):
        command = profiles.add_parser(name)
        command.add_argument("--backup-dir")
        command.add_argument("--evidence-dir")
        command.add_argument("--migration-evidence-dir")
        command.add_argument("--rollback-owner")
        command.add_argument("--rollback-trigger")
    rc = profiles.add_parser("rc", help="Run one existing RC lane")
    rc.add_argument("--lane", choices=RC_LANES, default="all")
    for name, script in (
        ("baseline", "run_release_baseline.sh"),
        ("migration", "run_migration_rehearsal.sh"),
        ("walkthrough", "run_end_to_end_release.sh"),
        ("confidence", "release_confidence.py"),
    ):
        command = profiles.add_parser(name, help="Forward to " + script)
        command.add_argument("backend_args", nargs=argparse.REMAINDER)
    return result


def external(path, root=ROOT):
    value = Path(path).expanduser().resolve()
    root = root.resolve()
    if value == root or root in value.parents:
        raise ValueError("Release evidence must be outside the repository: %s" % value)
    return value


def invoke(argv, env, root=ROOT):
    """One execution boundary: argv (no shell), repository cwd, inherited streams."""
    print("[release] " + " ".join(str(arg) for arg in argv), flush=True)
    subprocess.run([str(arg) for arg in argv], cwd=root, env=env, check=True)


def revision(root=ROOT):
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()


def run(args, env=None, execute=invoke, get_revision=revision, root=ROOT):
    env = dict(os.environ if env is None else env)
    python = sys.executable

    def command(*argv):
        execute(list(argv), env, root)

    def script(name, *argv):
        command("bash", "scripts/ci/" + name, *argv)

    if args.profile == "rc":
        script("run_rc_validation.sh", args.lane)
        return
    if args.profile in ("baseline", "migration", "walkthrough", "confidence"):
        forwarded = list(args.backend_args)
        if forwarded[:1] == ["--"]:
            forwarded.pop(0)
        if args.profile == "confidence":
            command(python, "ci/release_confidence.py", *forwarded)
        else:
            backend = {
                "baseline": "run_release_baseline.sh",
                "migration": "run_migration_rehearsal.sh",
                "walkthrough": "run_end_to_end_release.sh",
            }[args.profile]
            script(backend, *forwarded)
        return

    backup = args.backup_dir or env.get("RELEASE_BACKUP_DIR")
    owner = args.rollback_owner or env.get("ROLLBACK_OWNER")
    trigger = args.rollback_trigger or env.get("ROLLBACK_TRIGGER")
    if args.profile == "qualification" and not all((backup, owner, trigger)):
        raise ValueError("Qualification requires an approved backup, rollback owner and rollback trigger.")
    if backup and not all((owner, trigger)):
        raise ValueError("Migration requires rollback owner and rollback trigger; no partial rehearsal is accepted.")
    if backup and not Path(backup).expanduser().is_dir():
        raise ValueError("Backup directory does not exist: %s" % backup)
    sha = get_revision(root)
    temp = Path(env.get("TMPDIR", "/tmp"))
    evidence = external(args.evidence_dir or env.get("RELEASE_BASELINE_EVIDENCE_DIR")
                        or temp / "sports-federation-release-baseline" / sha, root)
    env["RELEASE_BASELINE_EVIDENCE_DIR"] = str(evidence)
    migration = external(args.migration_evidence_dir or env.get("MIGRATION_EVIDENCE_DIR")
                         or temp / "sports-federation-migration" / sha, root)
    if backup:
        backup = str(Path(backup).expanduser().resolve())
        env.update(RELEASE_BACKUP_DIR=backup, ROLLBACK_OWNER=owner, ROLLBACK_TRIGGER=trigger)

    if args.profile == "candidate":
        command(python, "ci/check_rc_product_readiness.py")
        command(python, "ci/check_rc_usability.py")
    else:
        command(python, "ci/check_always_invisible_fields.py")
        command(python, "ci/check_reliability_contract.py")
    script("run_release_baseline.sh")
    if args.profile in ("readiness", "qualification"):
        command(python, "ci/check_release_evidence.py", "--evidence-dir", evidence,
                "--commit", sha, "--require-passing")
        logs = [evidence / "logs" / (lane + ".log") for lane in ("focus", "install", "full")]
        logs = [path for path in logs if path.is_file()]
        if not logs:
            raise ValueError("No browser-capable release logs were produced.")
        command(python, "ci/check_browser_release_log.py", *logs)
    if backup:
        script("run_migration_rehearsal.sh", "--backup-dir", backup,
               "--evidence-dir", migration, "--rollback-owner", owner,
               "--rollback-trigger", trigger, "--yes")
    if args.profile == "qualification":
        command(python, "ci/check_release_signoff.py", "--baseline", evidence / "summary.json",
                "--migration", migration / "manifest.json", "--commit", sha)
        print("Release qualification passed for " + sha)
    elif args.profile == "candidate" and not backup:
        print("Candidate automation completed; migration and release qualification were NOT performed.")
    elif args.profile == "readiness":
        print("Release readiness evidence validated for " + sha + "; qualification remains separate.")


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        run(args)
    except subprocess.CalledProcessError as error:
        return error.returncode if error.returncode > 0 else 1
    except (ValueError, OSError) as error:
        print("Release runner: " + str(error), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Release runner interrupted; use the backend's cleanup command for retained resources.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
