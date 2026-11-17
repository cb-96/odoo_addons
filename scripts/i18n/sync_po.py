#!/usr/bin/env python3
"""Create and update the language files of every module from its template.

For each ``<module>/i18n/<module>.pot`` and each language in
``i18n/languages.json`` this keeps ``<module>/i18n/<code>.po`` in step with the
template: new texts are added untranslated, removed texts are dropped,
references and flags follow the template, translations are kept. A missing
language file is created, so adding a language is one registry entry and one
run of this script. The glossary (``i18n/glossary``) is handled the same way.

Weblate's "Update PO files to match POT" add-on does the same on its side;
running this locally gives identical files.

Usage:
    python scripts/i18n/sync_po.py                 # all languages
    python scripts/i18n/sync_po.py --language de   # one language
    python scripts/i18n/sync_po.py --check         # report only, write nothing
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pofile  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "i18n" / "languages.json"


def languages(only=None):
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    codes = [language["code"] for language in data["languages"]]
    if only:
        if only not in codes:
            raise SystemExit("%s is not in %s" % (only, REGISTRY.relative_to(ROOT)))
        return [only]
    return codes


def templates():
    """(component name, template path) for every module and the glossary."""
    found = []
    for pot in sorted(ROOT.glob("sports_federation_*/i18n/*.pot")):
        module = pot.parent.parent.name
        if pot.stem == module:
            found.append((module, pot))
    glossary = ROOT / "i18n" / "glossary" / "glossary.pot"
    if glossary.exists():
        found.append(("glossary", glossary))
    return found


def merge(template: pofile.Catalog, existing, language: str, component: str):
    previous = existing.by_msgid() if existing else {}
    entries = []
    for source in template.entries:
        old = previous.get(source.msgid)
        entries.append(
            pofile.add_code_markers(
                pofile.Entry(
                    msgid=source.msgid,
                    msgstr=old.msgstr if old else "",
                    comments=list(source.comments),
                    references=list(source.references),
                    flags=[flag for flag in source.flags if flag != "fuzzy"],
                )
            )
        )
    header = (
        existing.header
        if existing
        else pofile.Entry(
            msgid="",
            msgstr=pofile.header_text(language, component),
            comments=[
                "Translation of Odoo Server.",
                "This file contains the translation of the following modules:",
                "\t* %s" % component,
                "",
            ],
        )
    )
    return pofile.Catalog(header=header, entries=entries)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--language", help="only this language code")
    parser.add_argument("--check", action="store_true", help="write nothing")
    args = parser.parse_args()
    codes = languages(args.language)
    found = templates()
    if not found:
        print("No templates found. Run scripts/i18n/export_pot.sh first.")
        return 1
    changed = 0
    for component, pot in found:
        template = pofile.read(pot)
        for code in codes:
            path = pot.parent / ("%s.po" % code)
            existing = pofile.read(path) if path.exists() else None
            merged = merge(template, existing, code, component)
            before = path.read_text(encoding="utf-8") if path.exists() else None
            if args.check:
                stale = existing is None or [e.msgid for e in existing.entries] != [
                    e.msgid for e in merged.entries
                ]
                if stale:
                    changed += 1
                    print("out of date: %s" % path.relative_to(ROOT))
                continue
            pofile.write(merged, path)
            if before != path.read_text(encoding="utf-8"):
                changed += 1
                print(
                    "%s %s"
                    % (
                        "created" if before is None else "updated",
                        path.relative_to(ROOT),
                    )
                )
    if args.check:
        print("%s language file(s) out of date." % changed)
        return 1 if changed else 0
    print("%s language file(s) written." % changed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
