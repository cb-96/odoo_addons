#!/usr/bin/env python3
"""OWL templates must not reuse a component getter as a loop or t-set name.

In an OWL template, ``t-foreach ... t-as="day"`` cannot shadow a getter called
``day`` on the component: the getter wins, so every loop item silently shows
the getter's value. The match board's game-day buttons all showed the first
day because of this.
"""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = re.compile(r'static\s+template\s*=\s*["\']([^"\']+)["\']')
CLASS = re.compile(r"\bclass\s+\w+\s+extends\s+\w+\s*\{")
GETTER = re.compile(r"^\s*(?:static\s+)?get\s+([A-Za-z_$][\w$]*)\s*\(\s*\)\s*\{", re.M)


def component_getters():
    """{template name: set of getter names} for every OWL component."""
    result = {}
    for path in ROOT.glob("*/static/src/**/*.js"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        starts = [match.start() for match in CLASS.finditer(text)] + [len(text)]
        for start, end in zip(starts, starts[1:]):
            body = text[start:end]
            template = TEMPLATE.search(body)
            if template:
                result.setdefault(template.group(1), set()).update(GETTER.findall(body))
    return result


def template_names(element):
    for node in element.iter():
        for attribute in ("t-as", "t-set"):
            name = node.get(attribute)
            if name:
                yield attribute, name, node


def main():
    getters = component_getters()
    errors = []
    for path in ROOT.glob("*/static/src/**/*.xml"):
        try:
            tree = ET.parse(path)
        except ET.ParseError:
            continue
        for template in tree.getroot().iter():
            name = template.get("t-name")
            if not name or name not in getters:
                continue
            for attribute, variable, _node in template_names(template):
                if variable in getters[name]:
                    errors.append(
                        f'{path.relative_to(ROOT)}: {name} uses {attribute}="{variable}" '
                        f"but the component has a getter named {variable!r}"
                    )
    if errors:
        print(
            "OWL template variables shadow component getters:\n- "
            + "\n- ".join(errors),
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"OWL template shadowing check passed ({len(getters)} components).")


if __name__ == "__main__":
    main()
