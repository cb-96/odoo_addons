#!/usr/bin/env python3
"""Keep release qualification focused and broad upstream tests separate."""
from pathlib import Path
import re
import sys
ROOT = Path(__file__).resolve().parents[1]
RC = ROOT / "scripts/ci/run_rc_validation.sh"
BASELINE = ROOT / "scripts/ci/run_release_baseline.sh"
def violations(root: Path = ROOT) -> list[str]:
    rc=(root/RC.relative_to(ROOT)).read_text(encoding="utf-8")
    baseline=(root/BASELINE.relative_to(ROOT)).read_text(encoding="utf-8")
    failures=[]
    match=re.search(r"required_lanes=\(\n(?P<body>.*?)\n\)",baseline,re.DOTALL)
    lanes=match.group("body") if match else ""
    for diagnostic in ("core","portal","public","upstream"):
        if re.search(rf"^\s*{diagnostic}\s*$",lanes,re.MULTILINE): failures.append(f"{diagnostic} must not be a mandatory baseline lane")
    if "acceptance) run_tags 'sf_operator_acceptance'" not in rc: failures.append("acceptance must not duplicate browser release-focus tags")
    if "focus) run_tags 'sf_browser_competition_lifecycle" not in rc: failures.append("focus browser/release tags are missing")
    if '--test-enable --test-tags "$federation_test_tags"' not in rc: failures.append("install must run federation-scoped tests")
    if 'full) run_tags_on "$upgrade_db_name" "$federation_test_tags"' not in rc: failures.append("full must test the upgraded database with federation tags")
    if "upstream) run_tags 'standard'" not in rc: failures.append("broad standard tests need an explicit upstream lane")
    if "run_rc_validation.sh prepare-upgrade" not in baseline: failures.append("upgrade preparation must not rerun install tests")
    return failures
def main()->int:
    failures=violations()
    if failures:
        print("RC test-scope contract failed:",file=sys.stderr)
        for failure in failures: print(f"- {failure}",file=sys.stderr)
        return 1
    print("RC test-scope contract passed."); return 0
if __name__ == "__main__": raise SystemExit(main())
