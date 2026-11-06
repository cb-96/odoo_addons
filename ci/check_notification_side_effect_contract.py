#!/usr/bin/env python3
"""Structural prohibition of SMTP in business-action producers.

Recipient routing and failure behavior are tested by ci.test_notification_outbox."""

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
DISPATCHER = ROOT / "sports_federation_notifications/models/notification_dispatcher.py"
SERVICE = ROOT / "sports_federation_notifications/models/notification_service.py"


def violations(root=ROOT):
    dispatcher = (root / DISPATCHER.relative_to(ROOT)).read_text(encoding="utf-8")
    service = (root / SERVICE.relative_to(ROOT)).read_text(encoding="utf-8")
    failures = []
    for name, text in (("dispatcher", dispatcher), ("service", service)):
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "send":
                failures.append(f"{name} sends SMTP inside a business action")
            if node.func.attr == "send_mail":
                flag = next((kw.value for kw in node.keywords if kw.arg == "force_send"), None)
                if not isinstance(flag, ast.Constant) or flag.value is not False:
                    failures.append(f"{name} must explicitly queue template mail")
    return failures


def main():
    failures = violations()
    if failures:
        print("Notification side-effect contract failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Notification queue structure passed; behavioral and ORM tests are separate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
