#!/usr/bin/env python3
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors = []
seen = {}
header = [
    "id",
    "name",
    "model_id:id",
    "group_id:id",
    "perm_read",
    "perm_write",
    "perm_create",
    "perm_unlink",
]
for path in sorted(ROOT.glob("sports_federation_*/security/ir.model.access.csv")):
    rows = list(csv.reader(path.open(newline="", encoding="utf-8")))
    if not rows or rows[0] != header:
        errors.append(f"{path.relative_to(ROOT)}: invalid header")
        continue
    for n, row in enumerate(rows[1:], 2):
        if not row or not any(v.strip() for v in row):
            continue
        if len(row) != 8:
            errors.append(
                f"{path.relative_to(ROOT)}:{n}: expected 8 columns, got {len(row)}"
            )
            continue
        xmlid, _name, model, group, *perms = row
        if not xmlid:
            errors.append(f"{path.relative_to(ROOT)}:{n}: empty external id")
        if xmlid in seen:
            errors.append(
                f"duplicate ACL id {xmlid}: {seen[xmlid]} and {path.relative_to(ROOT)}:{n}"
            )
        seen[xmlid] = f"{path.relative_to(ROOT)}:{n}"
        if not model.startswith("model_") and ".model_" not in model:
            errors.append(f"{path.relative_to(ROOT)}:{n}: invalid model id {model}")
        if group and not (
            group.startswith("group_")
            or ".group_" in group
            or group == "base.group_portal"
        ):
            errors.append(f"{path.relative_to(ROOT)}:{n}: invalid group id {group}")
        if any(v not in ("0", "1") for v in perms):
            errors.append(f"{path.relative_to(ROOT)}:{n}: permissions must be 0 or 1")
if errors:
    print("ACL CSV integrity failed:\n- " + "\n- ".join(errors))
    sys.exit(1)
print(f"ACL CSV integrity passed for {len(seen)} access records.")
