#!/usr/bin/env python3
import ast
from pathlib import Path
import re
import sys
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
NAVIGATION = ROOT / "docs/user-guide/backend-navigation.md"
WORKFLOW = ROOT / "docs/user-guide/competition-workflow.md"
ROOT_MENU = "sports_federation_base.menu_federation_root"
ADVANCED_GROUP = "sports_federation_base.group_federation_advanced_operator"
TOP_LEVEL = (
    "Needs Attention",
    "Competitions",
    "Clubs & People",
    "Match Operations",
    "Publishing",
    "Finance & Assurance",
    "Reporting",
    "Administration",
)
REQUIRED_OPERATOR_PATHS = (
    ("Federation", "Competitions", "Competitions"),
    ("Federation", "Clubs & People", "Clubs"),
    ("Federation", "Clubs & People", "Teams"),
    ("Federation", "Match Operations", "Game Days"),
    ("Federation", "Reporting", "Operational Health"),
)
REQUIRED_ADVANCED_PATHS = (
    ("Federation", "Competitions", "Planning Tools", "Registration Desk"),
    ("Federation", "Competitions", "Planning Tools", "Format Studio"),
    ("Federation", "Competitions", "Planning Tools", "Calendar Planner"),
    ("Federation", "Competitions", "Planning Tools", "Schedule Planner"),
    ("Federation", "Publishing", "Schedules to Review"),
    ("Federation", "Administration", "Configuration", "Rule Sets"),
    ("Federation", "Administration", "System", "All Tasks"),
    ("Federation", "Administration", "System", "Operational Jobs"),
    ("Federation", "Administration", "System", "Competition Role Assignments"),
)
FORBIDDEN_TOP_LEVEL = {
    "Setup",
    "Planning",
    "Competition Workflow",
    "Match Day",
    "Publication",
    "Insights",
    "Reports",
}
# Area > section > item. Odoo renders deeper levels as flattened headers.
MAX_DEPTH_BELOW_ROOT = 3
# Leaf entries a Federation Manager without Advanced Federation Tools sees.
ORDINARY_LEAF_BUDGET = 12
# Groups held by an ordinary Federation Manager.
ORDINARY_GROUPS = {
    "base.group_user",
    "sports_federation_base.group_federation_user",
    "sports_federation_base.group_federation_manager",
}


def _manifest(module_dir):
    path = module_dir / "__manifest__.py"
    return ast.literal_eval(path.read_text(encoding="utf-8")) if path.exists() else None


def load_order():
    manifests = {}
    for module_dir in sorted(ROOT.glob("sports_federation_*")):
        manifest = _manifest(module_dir)
        if manifest is not None:
            manifests[module_dir.name] = manifest
    order, seen = [], set()

    def visit(name):
        if name in seen or name not in manifests:
            return
        seen.add(name)
        for dependency in manifests[name].get("depends", []):
            visit(dependency)
        order.append(name)

    for name in sorted(manifests):
        visit(name)
    return [(name, manifests[name]) for name in order]


def _qualify(module, ref):
    return ref if not ref or "." in ref else f"{module}.{ref}"


def _groups(module, value):
    value = value or ""
    if value.lstrip().startswith("["):
        return set(re.findall(r"ref\('([^']+)'\)", value))
    return {_qualify(module, item.strip()) for item in value.split(",") if item.strip()}


def index():
    """Resolve the final menu map in install order, like Odoo does."""
    records = {}
    for module, manifest in load_order():
        for data_file in manifest.get("data", []):
            if not data_file.endswith(".xml"):
                continue
            path = ROOT / module / data_file
            try:
                tree = ElementTree.parse(path)
            except ElementTree.ParseError as exc:
                raise RuntimeError(f"cannot parse {path}: {exc}") from exc
            for node in tree.iter():
                if node.tag == "menuitem" and node.get("id"):
                    xmlid = _qualify(module, node.get("id"))
                    record = records.setdefault(
                        xmlid, {"name": "", "parent": "", "sequence": 10, "groups": set(), "action": ""}
                    )
                    record["name"] = node.get("name", record["name"])
                    record["parent"] = _qualify(module, node.get("parent", "")) or record["parent"]
                    record["action"] = _qualify(module, node.get("action", "")) or record["action"]
                    if node.get("sequence"):
                        record["sequence"] = int(node.get("sequence"))
                    if node.get("groups"):
                        record["groups"] |= _groups(module, node.get("groups"))
                elif node.tag == "record" and node.get("model") == "ir.ui.menu" and node.get("id"):
                    xmlid = _qualify(module, node.get("id"))
                    record = records.setdefault(
                        xmlid, {"name": "", "parent": "", "sequence": 10, "groups": set(), "action": ""}
                    )
                    for field in node.findall("field"):
                        name = field.get("name")
                        if name == "name" and field.text:
                            record["name"] = field.text.strip()
                        elif name == "parent_id" and field.get("ref"):
                            record["parent"] = _qualify(module, field.get("ref"))
                        elif name == "action" and field.get("ref"):
                            record["action"] = _qualify(module, field.get("ref"))
                        elif name == "sequence" and field.text:
                            record["sequence"] = int(field.text.strip())
                        elif name in {"groups_id", "group_ids"}:
                            record["groups"] = _groups(module, field.get("eval"))
    for record in records.values():
        record["advanced"] = ADVANCED_GROUP in record["groups"]
    return records


def ancestors(records, xmlid):
    chain, seen = [], set()
    parent = records[xmlid]["parent"]
    while parent in records and parent not in seen:
        seen.add(parent)
        chain.append(parent)
        parent = records[parent]["parent"]
    return chain


def under_root(records):
    return {
        xmlid: record
        for xmlid, record in records.items()
        if xmlid != ROOT_MENU and ROOT_MENU in ancestors(records, xmlid)
    }


def ordinary_leaves(records):
    """Leaves visible to a Federation Manager without specialist or debug groups."""
    visible = []
    for xmlid, record in under_root(records).items():
        if not record["action"]:
            continue
        chain = [xmlid] + ancestors(records, xmlid)
        if all(
            not records[item]["groups"] or records[item]["groups"] & ORDINARY_GROUPS
            for item in chain
        ):
            visible.append(xmlid)
    return visible


def structure_errors(records):
    errors = []
    tree = under_root(records)
    children = {}
    for xmlid, record in tree.items():
        children.setdefault(record["parent"], []).append(xmlid)
    for xmlid, record in tree.items():
        depth = ancestors(records, xmlid).index(ROOT_MENU) + 1
        if depth > MAX_DEPTH_BELOW_ROOT:
            errors.append(f"{xmlid} is nested {depth} levels below Federation")
        if record["action"] and children.get(xmlid):
            errors.append(f"{xmlid} has an action and child menus; Odoo cannot open it")
        if not record["action"] and not children.get(xmlid):
            errors.append(f"{xmlid} is an empty menu folder")
    actions = {}
    for xmlid, record in tree.items():
        if record["action"]:
            actions.setdefault(record["action"], []).append(xmlid)
    for action, xmlids in actions.items():
        if len(xmlids) > 1:
            errors.append(f"{action} is exposed by several menus: {sorted(xmlids)}")
    for parent, xmlids in children.items():
        names = [tree[xmlid]["name"] for xmlid in xmlids]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            errors.append(f"{parent} has duplicate entries: {sorted(duplicates)}")
    leaves = ordinary_leaves(records)
    if len(leaves) > ORDINARY_LEAF_BUDGET:
        errors.append(
            f"ordinary managers see {len(leaves)} menu entries, budget is "
            f"{ORDINARY_LEAF_BUDGET}: {sorted(leaves)}"
        )
    return errors


def path_exists(records, labels):
    for record in records.values():
        if record["name"] != labels[-1]:
            continue
        names = [record["name"]]
        parent = record["parent"]
        visited = set()
        while parent in records and parent not in visited:
            visited.add(parent)
            record = records[parent]
            names.append(record["name"])
            parent = record["parent"]
        if tuple(reversed(names)) == labels:
            return True
    return False


def main():
    records = index()
    navigation = NAVIGATION.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    errors = structure_errors(records)

    top_level = tuple(
        record["name"]
        for record in sorted(
            (record for record in records.values() if record["parent"] == ROOT_MENU),
            key=lambda record: (record["sequence"], record["name"]),
        )
    )
    if top_level != TOP_LEVEL:
        errors.append(f"root work areas are {top_level!r}, expected {TOP_LEVEL!r}")
    stale = FORBIDDEN_TOP_LEVEL.intersection(top_level)
    if stale:
        errors.append("obsolete root categories remain: " + ", ".join(sorted(stale)))

    for labels in REQUIRED_OPERATOR_PATHS + REQUIRED_ADVANCED_PATHS:
        rendered = " > ".join(labels)
        if not path_exists(records, labels):
            errors.append(f"menu path missing: {rendered}")
        if rendered not in navigation and rendered not in workflow:
            errors.append(f"documented path missing: {rendered}")

    competition_root = "sports_federation_base.menu_federation_competitions"
    ordinary_competition_entries = sorted(
        record["name"]
        for record in records.values()
        if record["parent"] == competition_root and not record["advanced"]
    )
    if ordinary_competition_entries not in (["Competition Hub"], ["Competitions"]):
        errors.append(
            "ordinary competition entries are "
            f"{ordinary_competition_entries!r}, expected only Competition Hub"
        )

    for label in TOP_LEVEL:
        if f"**{label}**" not in navigation:
            errors.append(f"navigation purpose is undocumented: {label}")

    setup_view = (
        ROOT / "sports_federation_setup_flow/views/competition_setup_views.xml"
    ).read_text(encoding="utf-8")
    consolidation_view = (
        ROOT / "sports_federation_setup_flow/views/setup_consolidation_views.xml"
    ).read_text(encoding="utf-8")
    keyboard_tour = (
        ROOT
        / "sports_federation_demo/static/tests/tours/keyboard_competition_setup_tour.js"
    ).read_text(encoding="utf-8")
    if "data-keyboard-competition-setup" in setup_view + consolidation_view:
        errors.append(
            "setup views must use an Odoo-supported CSS class hook, not a custom XML attribute"
        )
    if (
        "o_competition_setup_action" not in setup_view
        or "o_competition_setup_action" not in consolidation_view
    ):
        errors.append(
            "setup action buttons must expose the o_competition_setup_action CSS hook"
        )
    if (
        '<xpath expr="//list" position="inside">' in consolidation_view
        and "<header>" in consolidation_view
    ):
        errors.append(
            "list headers must be inserted before a list field for Odoo 19 Relax NG compatibility"
        )
    if '".o_competition_setup_action"' not in keyboard_tour:
        errors.append(
            "keyboard setup tour must target the supported setup action CSS hook"
        )

    if errors:
        print("Federation backend navigation contract failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Federation backend navigation structure passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
