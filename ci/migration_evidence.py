#!/usr/bin/env python3
"""Seal and verify real migration/rollback artifacts; never execute a restore.

Checksums bind recorded artifacts, not an independent attestation of execution.
Only the approved isolated rehearsal backend may produce passing evidence.
"""

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

try:
    from .compare_migration_invariants import compare
except ImportError:
    from compare_migration_invariants import compare

CONTRACT = Path(__file__).resolve().parent / "release_invariants.json"

REQUIRED = (
    "before-upgrade.json",
    "after-upgrade.json",
    "rollback.json",
    "invariant-comparison.json",
    "restore-before-upgrade.txt",
    "restore-rollback.txt",
    "upgrade.json",
    "operator-acceptance.json",
    "upgrade.log",
    "operator-acceptance.log",
)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read_object(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(str(path) + ": expected a JSON object")
    return value


def artifacts(root, commit=None):
    """Validate restore evidence and recompute invariants from snapshots."""
    errors = []
    snapshots = {}
    contract = read_object(CONTRACT)
    for name in REQUIRED:
        path = (root / name).resolve()
        if root not in path.parents or not path.is_file():
            errors.append("Missing or escaped migration artifact: " + name)
            continue
        try:
            if name.endswith(".json"):
                value = read_object(path)
                if value.get("schema_version") != (
                    2 if name in ("upgrade.json", "operator-acceptance.json") else 1
                ):
                    errors.append("Unsupported migration artifact schema: " + name)
                snapshots[name] = value
            elif (
                name.startswith("restore-")
                and "filestore_restored=yes" not in path.read_text().splitlines()
            ):
                errors.append("Full filestore restoration not demonstrated: " + name)
        except (OSError, ValueError, TypeError) as error:
            errors.append(str(error))
    comparison = snapshots.get("invariant-comparison.json", {})
    if comparison.get("status") != "passed" or comparison.get("differences") != []:
        errors.append("Migration invariant comparison is not passing")
    before = snapshots.get("before-upgrade.json")
    after = snapshots.get("after-upgrade.json")
    rollback = snapshots.get("rollback.json")
    if all(isinstance(value, dict) for value in (before, after, rollback)):
        for name, value in (
            ("before", before),
            ("after", after),
            ("rollback", rollback),
        ):
            if not isinstance(value.get("counts"), dict) or not value["counts"]:
                errors.append(name + " snapshot has no invariant counts")
            if (
                not isinstance(value.get("zero_checks"), dict)
                or not value["zero_checks"]
            ):
                errors.append(name + " snapshot has no integrity checks")
        for name, value in (
            ("before", before),
            ("after", after),
            ("rollback", rollback),
        ):
            for section in ("counts", "zero_checks"):
                if isinstance(value.get(section), dict):
                    if set(value[section]) != set(contract[section]):
                        errors.append(
                            name
                            + " snapshot does not cover the invariant contract: "
                            + section
                        )
                    if any(
                        type(number) is not int or number < 0
                        for number in value[section].values()
                    ):
                        errors.append(
                            name + " snapshot contains invalid numeric invariants"
                        )
        expected_modes = {
            key: contract.get("count_modes", {}).get(key, "exact")
            for key in contract["counts"]
        }
        if before.get("count_modes") != expected_modes:
            errors.append(
                "Before snapshot count modes differ from the invariant contract"
            )
        try:
            differences = compare(before, after, "after") + compare(
                before, rollback, "rollback", force_exact=True
            )
            if differences:
                errors.append("Recomputed migration/rollback invariants differ")
        except (ValueError, TypeError, AttributeError) as error:
            errors.append("Invalid invariant snapshots: " + str(error))
    for name, lane, log_name in (
        ("upgrade.json", "migration-upgrade", "upgrade.log"),
        (
            "operator-acceptance.json",
            "role-separated-acceptance",
            "operator-acceptance.log",
        ),
    ):
        record = snapshots.get(name, {})
        if record.get("commit") != commit or record.get("lane") != lane:
            errors.append("Runtime lane belongs to another candidate or lane: " + name)
        if (
            record.get("status") != "passed"
            or type(record.get("exit_code")) is not int
            or record["exit_code"] != 0
        ):
            errors.append("Runtime lane is not passing: " + name)
        log = (root / log_name).resolve()
        recorded_log = record.get("log", {})
        if (
            root in log.parents
            and log.is_file()
            and (
                not isinstance(recorded_log, dict)
                or recorded_log.get("sha256") != digest(log)
                or log.stat().st_size == 0
            )
        ):
            errors.append(
                "Runtime lane log is empty or not bound to its evidence: " + name
            )
    return errors


def validate_bundle(directory, commit):
    root = Path(directory).resolve()
    errors = artifacts(root, commit)
    try:
        manifest_path = (root / "manifest.json").resolve()
        if root not in manifest_path.parents:
            raise ValueError("Migration manifest escapes its evidence directory")
        manifest = read_object(manifest_path)
        if manifest.get("schema_version") != 2:
            errors.append(
                "Migration manifest must be sealed schema 2; rerun the rehearsal"
            )
        if manifest.get("commit") != commit:
            errors.append("Migration manifest is not for the exact candidate commit")
        if manifest.get("invariants_contract_sha256") != digest(CONTRACT):
            errors.append("Migration invariant contract changed; rerun the rehearsal")
        if manifest.get("status") != "passed":
            errors.append("Migration manifest is not passing")
        for field in ("rollback_owner", "rollback_trigger"):
            if not isinstance(manifest.get(field), str) or not manifest[field].strip():
                errors.append("Migration manifest lacks " + field)
        checksums = manifest.get("artifact_sha256", {})
        if not isinstance(checksums, dict):
            checksums = {}
        for name in REQUIRED:
            path = (root / name).resolve()
            if (
                root in path.parents
                and path.is_file()
                and checksums.get(name) != digest(path)
            ):
                errors.append("Missing or changed artifact checksum: " + name)
        backup = manifest.get("backup", {})
        if (
            not isinstance(backup, dict)
            or not isinstance(backup.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", backup["sha256"])
        ):
            errors.append("Migration backup checksum is missing or malformed")
    except (OSError, ValueError, TypeError) as error:
        errors.append("Invalid migration manifest: " + str(error))
    return errors


def seal(directory, commit, backup, owner, trigger):
    root = Path(directory).resolve()
    if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
        raise ValueError("A full candidate commit hash is required")
    if not owner.strip() or not trigger.strip():
        raise ValueError("Rollback owner and trigger are required")
    errors = artifacts(root, commit)
    if errors:
        raise ValueError("; ".join(errors))
    manifest = {
        "schema_version": 2,
        "commit": commit,
        "status": "passed",
        "invariants_contract_sha256": digest(CONTRACT),
        "rollback_owner": owner.strip(),
        "rollback_trigger": trigger.strip(),
        "backup": {"path": str(Path(backup).resolve()), "sha256": digest(backup)},
        "artifacts": list(REQUIRED),
        "artifact_sha256": {name: digest(root / name) for name in REQUIRED},
    }
    temporary = root / "manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    temporary.replace(root / "manifest.json")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("seal", "verify"):
        command = sub.add_parser(name)
        command.add_argument("--evidence-dir", type=Path, required=True)
        command.add_argument("--commit", required=True)
        if name == "seal":
            command.add_argument("--backup", type=Path, required=True)
            command.add_argument("--rollback-owner", required=True)
            command.add_argument("--rollback-trigger", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "seal":
            seal(
                args.evidence_dir,
                args.commit,
                args.backup,
                args.rollback_owner,
                args.rollback_trigger,
            )
        errors = validate_bundle(args.evidence_dir, args.commit)
        if errors:
            print(
                "Migration evidence rejected:\n- " + "\n- ".join(errors),
                file=sys.stderr,
            )
            return 1
    except (OSError, ValueError, TypeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print("Exact-commit migration artifact evidence verified for " + args.commit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
