#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    "sports_federation_base/models/retention_evidence.py": (
        "class FederationRetentionPolicy",
        "candidate_count",
        "record_failure_durable",
        "never_run",
        "overdue",
    ),
    "sports_federation_base/views/retention_evidence_views.xml": (
        "Retention and Recovery",
        "Needs Attention",
        "Skipped or Failed Records",
    ),
    "sports_federation_notifications/models/notification_log.py": (
        "_retention_candidate_count",
        "record_execution",
    ),
    "sports_federation_import_tools/models/integration_delivery_retention_mixin.py": (
        "_retention_candidates",
        "attachment_count",
    ),
    "sports_federation_reporting/models/report_schedule.py": (
        "_generated_file_retention_candidates",
        "record_execution",
    ),
}


def main():
    errors = []
    for relative, tokens in REQUIRED.items():
        path = ROOT / relative
        content = path.read_text() if path.is_file() else ""
        if not content:
            errors.append(f"missing {relative}")
        errors.extend(
            f"{relative} missing {token!r}" for token in tokens if token not in content
        )
    if errors:
        print("Retention visibility contract failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Retention visibility contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
