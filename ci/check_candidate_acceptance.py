import argparse
import hashlib
import json
import re
from pathlib import Path

REQUIRED = (
    "install",
    "upgrade",
    "migration",
    "rollback",
    "concurrency",
    "browser",
    "novice",
    "mobile",
    "keyboard",
)


def validate(record, commit, directory):
    errors = []
    if not re.fullmatch(r"[0-9a-f]{40}", commit) or record.get("commit") != commit:
        errors.append("Evidence must match the exact full candidate commit.")
    for name in REQUIRED:
        case = record.get("checks", {}).get(name, {})
        if case.get("status") != "passed" or not case.get("executed_at"):
            errors.append(name + ": execution not passed or timestamp missing")
        if name in {"novice", "mobile", "keyboard"}:
            if not all(case.get(k) for k in ("observer", "participant", "device")):
                errors.append(
                    name + ": actual observer, participant and device required"
                )
        elif not case.get("command"):
            errors.append(name + ": executed command required")
        if not case.get("artifacts"):
            errors.append(name + ": evidence artifacts required")
        for artifact in case.get("artifacts", []):
            path = (directory / artifact.get("path", "")).resolve()
            if not path.is_relative_to(directory.resolve()) or not path.is_file():
                errors.append(name + ": invalid artifact path")
            elif hashlib.sha256(path.read_bytes()).hexdigest() != artifact.get(
                "sha256"
            ):
                errors.append(name + ": artifact checksum mismatch")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    errors = validate(
        json.loads(args.evidence.read_text()), args.commit, args.evidence.parent
    )
    for error in errors:
        print(error)
    if errors:
        raise SystemExit(1)
    print(
        "Candidate evidence integrity passed; observed execution still requires accountable sign-off."
    )


if __name__ == "__main__":
    main()
