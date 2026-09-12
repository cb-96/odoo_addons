#!/usr/bin/env python3
"""Protect the non-blocking result-notification contract."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DISPATCHER = ROOT / "sports_federation_notifications/models/notification_dispatcher.py"
SERVICE = ROOT / "sports_federation_notifications/models/notification_service.py"


def violations(root=ROOT):
    dispatcher = (root / DISPATCHER.relative_to(ROOT)).read_text(encoding="utf-8")
    service = (root / SERVICE.relative_to(ROOT)).read_text(encoding="utf-8")
    failures = []
    required_dispatcher = (
        "notification_match = match.sudo()",
        "notification_match.home_team_id",
        "notification_match.away_team_id",
        "self._send_email_or_log(",
    )
    for token in required_dispatcher:
        if token not in dispatcher:
            failures.append(f"result notification is missing: {token}")
    if "except Exception" not in service:
        failures.append("notification service does not contain an integration failure boundary")
    if "failure_category" not in service or "operator_message" not in service:
        failures.append("notification failures do not persist operator feedback")
    return failures


def main():
    failures = violations()
    if failures:
        print("Notification side-effect contract failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Notification side-effect contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
