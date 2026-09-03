#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    errors = []
    portal = (
        (ROOT / "sports_federation_portal/views/portal_templates.xml")
        .read_text()
        .lower()
    )
    for text in ("no players found", "no teams found", "no action items"):
        if text not in portal:
            errors.append(f"missing empty state: {text}")
    quick = (
        ROOT / "sports_federation_portal/static/src/js/portal_quick_actions.js"
    ).read_text()
    for text in (
        "Copy direct link",
        "What happens next?",
        "Recent items",
        "MAX_RECENT = 8",
    ):
        if text not in quick:
            errors.append(f"missing quick action: {text}")
    if errors:
        print("RC usability failed:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1
    print("RC usability contracts passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
