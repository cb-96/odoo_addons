#!/usr/bin/env python3
"""Fail when a portal access right has no record rule behind it.

An ``ir.model.access`` row grants an operation on a whole model. For a portal
group, the only thing that keeps a club's user from reading (or writing) every
other club's records through the ORM (``/web/dataset/call_kw``) is a record
rule. Portal pages filter correctly, but the ORM does not use them.

Rule: for every ACL row of a portal group, each granted operation (read, write,
create, unlink) needs a record rule on that model that

- is global (no groups), or names that same group, and
- does not switch that operation off (``perm_<op>`` false).

Models that are public by design are listed in ``PUBLIC_BY_DESIGN`` with the
reason; the check also fails when an entry there is no longer needed.

A portal rule must also scope through ``user.portal_club_scope_ids`` or
``user.portal_team_scope_ids`` (current, whole-club or team tenures), never
through the raw ``user.representative_ids``, which includes ended tenures and
treats a team coach as a representative of the whole club.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
OPERATIONS = ("read", "write", "create", "unlink")

# (model xml name, group) -> why a record rule is not needed
PUBLIC_BY_DESIGN = {
    ("model_federation_season", "group_federation_portal_club"): (
        "season names and dates are shown on the public site; read only"
    ),
}


def is_portal_group(group: str) -> bool:
    name = group.rsplit(".", 1)[-1]
    return "portal" in name


def last(ref: str) -> str:
    return ref.rsplit(".", 1)[-1]


def acl_rows(root: Path):
    for path in sorted(root.glob("sports_federation_*/security/ir.model.access.csv")):
        with path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(line for line in stream if line.strip()):
                group = row.get("group_id:id", "")
                if not group or not is_portal_group(group):
                    continue
                granted = {
                    op for op in OPERATIONS if row.get(f"perm_{op}", "0").strip() == "1"
                }
                if granted:
                    yield path, row["id"], last(row["model_id:id"]), last(
                        group
                    ), granted


def _group_refs(record) -> set[str]:
    field = record.find("field[@name='groups']")
    if field is None:
        return set()
    return {
        last(match) for match in re.findall(r"ref\('([^']+)'\)", field.get("eval", ""))
    }


def _perm_enabled(record, op: str) -> bool:
    field = record.find(f"field[@name='perm_{op}']")
    if field is None:
        return True
    return (field.get("eval") or field.text or "").strip() not in ("False", "0", "")


def rules(root: Path):
    """(model xml name, groups, enabled operations) for every ir.rule record."""
    for path in sorted(root.glob("sports_federation_*/**/*.xml")):
        if "static" in path.parts:
            continue
        try:
            tree = etree.parse(str(path))
        except etree.XMLSyntaxError:
            continue
        for record in tree.iter("record"):
            if record.get("model") != "ir.rule":
                continue
            model = record.find("field[@name='model_id']")
            if model is None or not model.get("ref"):
                continue
            yield (
                last(model.get("ref")),
                _group_refs(record),
                {op for op in OPERATIONS if _perm_enabled(record, op)},
            )


def raw_representative_rules(root: Path):
    """Names of rules whose domain reads ``user.representative_ids`` directly."""
    for path in sorted(root.glob("sports_federation_*/**/*.xml")):
        if "static" in path.parts:
            continue
        try:
            tree = etree.parse(str(path))
        except etree.XMLSyntaxError:
            continue
        for record in tree.iter("record"):
            if record.get("model") != "ir.rule":
                continue
            domain = record.find("field[@name='domain_force']")
            if domain is not None and "user.representative_ids" in (domain.text or ""):
                yield path, record.get("id")


def check(root: Path, public_by_design=None) -> list[str]:
    public = PUBLIC_BY_DESIGN if public_by_design is None else public_by_design
    all_rules = list(rules(root))
    errors = []
    for path, rule_id in raw_representative_rules(root):
        errors.append(
            f"{path.relative_to(root).as_posix()}: rule {rule_id} uses "
            "user.representative_ids; use user.portal_club_scope_ids or "
            "user.portal_team_scope_ids"
        )
    used_exceptions = set()
    for path, acl_id, model, group, granted in acl_rows(root):
        for op in sorted(granted):
            covered = any(
                rule_model == model
                and (not groups or group in groups)
                and op in enabled
                for rule_model, groups, enabled in all_rules
            )
            if covered:
                continue
            if (model, group) in public and granted == {"read"}:
                used_exceptions.add((model, group))
                continue
            errors.append(
                f"{path.relative_to(root).as_posix()}: {acl_id} lets {group} "
                f"{op} every record of {model}; add a record rule for that group"
            )
    for key in sorted(set(public) - used_exceptions):
        errors.append(f"PUBLIC_BY_DESIGN entry {key} is not needed any more; remove it")
    return errors


def main() -> int:
    errors = check(ROOT)
    if errors:
        print("Portal record rule check failed:")
        for error in sorted(set(errors)):
            print(f"- {error}")
        return 1
    print("Portal record rule check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
