#!/usr/bin/env python3
"""Keep scheduling simple by default and optimisation tools in Advanced scheduling.

Contract (UX-05 / UX-06):

* the default schedule form leads with one status block and the two words
  "Must fix" and "Could improve";
* weighted fairness, the fairness score, calendar-fixture validation data and
  candidate comparison are advanced tools, never part of the default screen;
* hiding a tool must never hide the planner: no ``groups`` on the schedule form's
  ``<notebook>`` and the Assignments page stays ungated.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADVANCED = "sports_federation_base.group_federation_advanced_operator"
errors: list[str] = []


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def check_default_screen():
    text = read("sports_federation_scheduling/views/simple_scheduling_views.xml")
    for needle in ("Must fix", "Could improve", "simple_summary", "simple_checked"):
        if needle not in text:
            errors.append("simple_scheduling_views.xml lacks %r." % needle)
    if re.search(r"<xpath[^>]*//notebook[^>]*>\s*<attribute name=\"groups\"", text):
        errors.append("The schedule notebook itself must never be group gated.")
    if re.search(r"page\[@name=.assignments.\][^<]*>\s*<attribute name=\"groups\"", text):
        errors.append("The Assignments page must stay available to every planner.")
    if ADVANCED not in text:
        errors.append("Calendar fixtures must be gated to advanced operators.")
    base = read("sports_federation_scheduling/views/scheduling_views.xml")
    if re.search(r"<notebook[^>]*groups=", base):
        errors.append("scheduling_views.xml gates the whole notebook.")
    manifest = read("sports_federation_scheduling/__manifest__.py")
    if "views/simple_scheduling_views.xml" not in manifest:
        errors.append("The simple scheduling view is not in the manifest.")


def check_advanced_tools():
    fairness = read("sports_federation_scheduling/views/fairness_views.xml")
    for fragment in (
        'name="scheduling_fairness" groups="%s"' % ADVANCED,
        '<group string="Fairness formula" groups="%s"' % ADVANCED,
        '<field name="fairness_score" groups="%s"' % ADVANCED,
    ):
        if fragment not in fairness:
            errors.append("fairness_views.xml lacks the advanced gate %r." % fragment)
    visual = read("sports_federation_live_workspace/static/src/workspaces.xml")
    for fragment in (
        "Advanced scheduling: fairness preferences",
        "Advanced scheduling: compare two candidates",
        "Advanced scheduling: fairness score",
    ):
        if fragment not in visual:
            errors.append("The visual planner lacks %r." % fragment)
    for legacy in ("<h2>Blocking issues</h2>", "<h2>Fairness warnings</h2>"):
        if legacy in visual:
            errors.append("The visual planner still uses %s." % legacy)
    for word in ("<h2>Must fix</h2>", "<h2>Could improve</h2>"):
        if word not in visual:
            errors.append("The visual planner lacks %s." % word)


def main() -> int:
    check_default_screen()
    check_advanced_tools()
    if errors:
        print("Simple scheduling contract failed:")
        for error in errors:
            print("- %s" % error)
        return 1
    print("Simple scheduling contract passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
