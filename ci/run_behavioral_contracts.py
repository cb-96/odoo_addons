#!/usr/bin/env python3
"""One isolated behavioral gate; does not claim ORM or browser execution."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "ci.test_workflow_commands",
    "ci.test_task_projection",
    "ci.test_notification_outbox",
)


def main():
    sys.path.insert(0, str(ROOT))
    from ci.check_task_projection import violations as projection_structure
    from ci.check_notification_side_effect_contract import violations as queue_structure

    errors = projection_structure() + queue_structure()
    if errors:
        print("Structural violations:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1
    suite = unittest.TestSuite(
        unittest.defaultTestLoader.loadTestsFromName(name) for name in MODULES
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(
        "Executed isolated production-method contracts; ORM and browser suites were not run."
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
