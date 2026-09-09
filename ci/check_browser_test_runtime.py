#!/usr/bin/env python3
"""Verify that release browser dependencies are locked into the CI image."""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = "websocket-client==1.8.0"


def find_violations(root: Path = ROOT) -> list[str]:
    requirements = root / "requirements.txt"
    dockerfile = root / "ci/Dockerfile.odoo-ci"
    compose = root / "ci/docker-compose.ci.yaml"
    violations = []
    if not requirements.is_file() or EXPECTED not in requirements.read_text():
        violations.append(f"requirements.txt must lock {EXPECTED}")
    if not dockerfile.is_file():
        violations.append("the Odoo CI Dockerfile is missing")
    else:
        source = dockerfile.read_text()
        if "sports-federation-requirements.txt" not in source:
            violations.append("the Odoo CI image does not install project requirements")
        if "import websocket" not in source:
            violations.append("the Odoo CI image does not verify websocket-client")
    if not compose.is_file():
        violations.append("the CI Compose file is missing")
    else:
        source = compose.read_text()
        if not re.search(r"dockerfile:\s+ci/Dockerfile\.odoo-ci", source):
            violations.append("ci-odoo does not build the locked Odoo CI image")
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("Browser runtime contract failed:", file=sys.stderr)
        for violation in violations:
            print(f"- {violation}", file=sys.stderr)
        return 1
    print("Browser runtime contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
