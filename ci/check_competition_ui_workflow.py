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
REQUIRED_PATHS = (
    ("Federation", "Competitions", "Seasons"),
    ("Federation", "Competitions", "Season Competitions"),
    ("Federation", "Competitions", "Competition Operations", "Create Competition"),
    ("Federation", "Competitions", "Competition Operations", "Competition Overview"),
    ("Federation", "Competitions", "Competition Operations", "Registration Desk"),
    ("Federation", "Competitions", "Competition Operations", "Format Studio"),
    ("Federation", "Competitions", "Competition Operations", "Calendar Planner"),
    ("Federation", "Competitions", "Competition Operations", "Schedule Planner"),
    ("Federation", "Competitions", "Competition Operations", "Schedule Review Queue"),
    ("Federation", "Clubs & People", "Club Directory", "Clubs"),
    ("Federation", "Clubs & People", "Club Directory", "Teams"),
    ("Federation", "Match Operations", "Match-Day Control"),
    ("Federation", "Match Operations", "Matches"),
    ("Federation", "Match Operations", "Match Sheets"),
    ("Federation", "Publishing", "Approved Schedules"),
    ("Federation", "Publishing", "Schedule Publications"),
    ("Federation", "Publishing", "Standings"),
    ("Federation", "Finance & Assurance", "Finance"),
    ("Federation", "Finance & Assurance", "Compliance"),
    ("Federation", "Finance & Assurance", "Governance"),
    (
        "Federation",
        "Insights",
        "Reports & Insights",
        "Overview & Readiness",
        "Operational Health",
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
    for path in ROOT.glob("sports_federation_*/views/*.xml"):
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
            }
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

    for labels in REQUIRED_PATHS:
        rendered = " > ".join(labels)
        if not path_exists(records, labels):
            errors.append(f"menu path missing: {rendered}")
        if rendered not in navigation and rendered not in workflow:
            errors.append(f"documented path missing: {rendered}")

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
