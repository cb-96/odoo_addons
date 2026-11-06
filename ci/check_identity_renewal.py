#!/usr/bin/env python3
"""Keep identity backfill a finder, and renewal progress a read-only projection.

* the candidate queue may find and list duplicates but never merges one itself:
  merging stays in the reviewed identity decision;
* the backfill writes only the match key, through the lifecycle command token;
* renewal progress writes nothing and renewal approval stays ``action_activate``.
"""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MODULE = "sports_federation_member_services"
errors: list[str] = []


def read(relative):
    return (ROOT / MODULE / relative).read_text(encoding="utf-8")


def check_backfill():
    text = read("models/identity_backfill.py")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
            if "family_duplicate_of_id" in keys:
                errors.append("The candidate queue may not retire a duplicate; use the reviewed decision.")
            if "person_id" in keys and "player_id" not in keys:
                errors.append("The candidate queue may not relink a person.")
    if "command(" not in text or "family_match_key" not in text:
        errors.append("The backfill must write the match key through the lifecycle command.")
    if "federation.identity.review" not in text:
        errors.append("Candidates must be resolved through the reviewed identity decision.")
    if "federation.identity.decision" in text:
        errors.append("Only the reviewed identity merge may create identity decisions.")
    if "manager(self.env)" not in text:
        errors.append("Backfill actions must require membership administration permission.")
    if text.count("manager(self.env)") < 3:
        errors.append("run_backfill, action_review and action_dismiss must each check the permission.")


def check_renewal():
    text = read("models/renewal_progress.py")
    for forbidden in (".write(", ".create(", ".unlink(", "action_activate"):
        if forbidden in text:
            errors.append("renewal_progress.py is a projection and may not use %s." % forbidden)
    policy = read("renewal_policy.py")
    if "payment" not in policy.lower():
        errors.append("The renewal policy must state how payment is treated.")
    lifecycle = read("models/lifecycle.py")
    if "def action_activate" not in lifecycle:
        errors.append("Renewal approval must remain action_activate.")


def check_security_and_views():
    csv = read("security/ir.model.access.csv")
    rows = [line for line in csv.splitlines() if "model_federation_identity_candidate" in line]
    if len(rows) != 1 or "group_federation_manager" not in rows[0] or not rows[0].endswith(",1,1,1,0"):
        errors.append("The identity candidate queue must be manager-only and not deletable.")
    manifest = read("__manifest__.py")
    if "views/identity_backfill_views.xml" not in manifest:
        errors.append("The identity backfill views are not in the manifest.")
    views = read("views/identity_backfill_views.xml")
    if views.count("group_federation_manager") < 2:
        errors.append("The identity and renewal menus must be restricted to managers.")


def main() -> int:
    check_backfill()
    check_renewal()
    check_security_and_views()
    if errors:
        print("Identity and renewal contract failed:")
        for error in errors:
            print("- %s" % error)
        return 1
    print("Identity and renewal contract passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
