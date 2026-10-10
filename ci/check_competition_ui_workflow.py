#!/usr/bin/env python3
from pathlib import Path
import sys
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
NAVIGATION = ROOT / "docs/FEDERATION_BACKEND_NAVIGATION.md"
WORKFLOW = ROOT / "docs/COMPETITION_UI_WORKFLOW.md"
ROOT_MENU = "sports_federation_base.menu_federation_root"
TOP_LEVEL = (
    "Competitions",
    "Clubs & People",
    "Match Operations",
    "Publishing",
    "Finance & Assurance",
    "Insights",
    "Administration",
)
REQUIRED_OPERATOR_PATHS = (
    ("Federation", "Competitions", "Competition Hub"),
    ("Federation", "Clubs & People", "Club Directory", "Clubs"),
    ("Federation", "Clubs & People", "Club Directory", "Teams"),
    ("Federation", "Match Operations", "Match-Day Control"),
)
REQUIRED_ADVANCED_PATHS = (
    ("Federation", "Competitions", "Advanced Competition Tools", "Create Competition"),
    ("Federation", "Competitions", "Advanced Competition Tools", "Registration Desk"),
    ("Federation", "Competitions", "Advanced Competition Tools", "Format Studio"),
    ("Federation", "Competitions", "Advanced Competition Tools", "Calendar Planner"),
    ("Federation", "Competitions", "Advanced Competition Tools", "Schedule Planner"),
    ("Federation", "Competitions", "Advanced Competition Tools", "Schedule Review Queue"),
    (
        "Federation",
        "Administration",
        "Competition Audit & Recovery",
        "Role Assignments",
    ),
    ("Federation", "Administration", "Action Queue"),
    ("Federation", "Administration", "System Health", "Operational Job Health"),
)
FORBIDDEN_TOP_LEVEL = {
    "Setup",
    "Planning",
    "Competition Workflow",
    "Match Day",
    "Publication",
}


def index():
    records = {}
    paths = list(ROOT.glob("sports_federation_*/views/*.xml"))
    for path in paths:
        try:
            tree = ElementTree.parse(path)
        except ElementTree.ParseError as exc:
            raise RuntimeError(f"cannot parse {path}: {exc}") from exc
        module = path.parts[-3]
        for node in tree.iter("menuitem"):
            if not node.get("id"):
                continue
            rid = node.get("id")
            xmlid = rid if "." in rid else f"{module}.{rid}"
            parent = node.get("parent", "")
            parent = parent if not parent or "." in parent else f"{module}.{parent}"
            records[xmlid] = {
                "name": node.get("name", ""),
                "parent": parent,
                "sequence": int(node.get("sequence", "10")),
                "advanced": "group_federation_advanced_operator"
                in node.get("groups", ""),
            }
    # Explicit ir.ui.menu records update menus created in dependency addons.
    # Apply the aggregate application overrides last, matching supported install
    # order rather than relying on filesystem glob order.
    paths.sort(key=lambda path: (path.parts[-3] == "sports_federation_app", str(path)))
    for path in paths:
        try:
            tree = ElementTree.parse(path)
        except ElementTree.ParseError:
            continue
        module = path.parts[-3]
        for node in tree.iter("record"):
            if node.get("model") != "ir.ui.menu" or not node.get("id"):
                continue
            rid = node.get("id")
            xmlid = rid if "." in rid else f"{module}.{rid}"
            record = records.setdefault(
                xmlid, {"name": "", "parent": "", "sequence": 10, "advanced": False}
            )
            for field in node.findall("field"):
                name = field.get("name")
                if name == "name" and field.text:
                    record["name"] = field.text.strip()
                elif name == "parent_id" and field.get("ref"):
                    parent = field.get("ref")
                    record["parent"] = (
                        parent if "." in parent else f"{module}.{parent}"
                    )
                elif name == "sequence" and field.text:
                    record["sequence"] = int(field.text.strip())
                elif name == "groups_id":
                    record["advanced"] = (
                        "group_federation_advanced_operator"
                        in (field.get("eval") or "")
                    )
    return records


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
    errors = []

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
    if ordinary_competition_entries != ["Competition Hub"]:
        errors.append(
            "ordinary competition entries are "
            f"{ordinary_competition_entries!r}, expected only Competition Hub"
        )

    for label in TOP_LEVEL:
        if f"**{label}**" not in navigation:
            errors.append(f"navigation purpose is undocumented: {label}")

    if errors:
        print("Federation backend navigation contract failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("Federation backend navigation structure passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
