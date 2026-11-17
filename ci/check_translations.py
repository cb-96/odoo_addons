#!/usr/bin/env python3
"""Translation contract: language registry, PO files, and translatable messages.

* ``i18n/languages.json`` is the only list of languages; every ``.po`` file
  belongs to a registered language (or one of its Odoo regional codes).
* Every PO file parses, has a ``Language`` header and no duplicate texts.
* No translation changes placeholders or markup; such a translation would
  break a message or a page for everyone using that language.
* Language files follow their module template (``scripts/i18n/sync_po.py``).
* Completeness is reported per language and module group. Languages with
  status ``required`` fail the check when a text is untranslated.
* Portal messages passed to a page (``success=``, ``error=``,
  ``error_hint=``) must be translatable, not plain English literals.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "i18n"))
import pofile  # noqa: E402

REGISTRY = ROOT / "i18n" / "languages.json"
STATUSES = {"draft", "active", "required"}
MESSAGE_KEYWORDS = {"success", "error", "error_hint"}


def load_registry(errors):
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    languages = data.get("languages") or []
    codes = set()
    for language in languages:
        code = language.get("code", "")
        if not code or code in codes:
            errors.append("languages.json: missing or duplicate code %r" % code)
        codes.add(code)
        if language.get("status") not in STATUSES:
            errors.append(
                "languages.json: %s has unknown status %r"
                % (code, language.get("status"))
            )
        for odoo_code in language.get("odoo_codes") or []:
            if odoo_code.split("_")[0] != code:
                errors.append(
                    "languages.json: %s lists foreign Odoo code %s" % (code, odoo_code)
                )
    return data, languages


def components():
    found = []
    for pot in sorted(ROOT.glob("sports_federation_*/i18n/*.pot")):
        if pot.stem == pot.parent.parent.name:
            found.append((pot.stem, pot))
    glossary = ROOT / "i18n" / "glossary" / "glossary.pot"
    if glossary.exists():
        found.append(("glossary", glossary))
    return found


def group_of(module, groups):
    for group in groups:
        if group["modules"] == "*" or module in group["modules"]:
            return group["name"]
    return "Other"


def check_po_files(languages, errors, warnings):
    allowed = {}
    for language in languages:
        allowed[language["code"]] = language["code"]
        for odoo_code in language.get("odoo_codes") or []:
            allowed[odoo_code] = language["code"]
    catalogs = {}
    paths = sorted(ROOT.glob("sports_federation_*/i18n/*.po")) + sorted(
        (ROOT / "i18n" / "glossary").glob("*.po")
    )
    for path in paths:
        rel = path.relative_to(ROOT)
        if path.stem not in allowed:
            errors.append(
                "%s: language %r is not in i18n/languages.json" % (rel, path.stem)
            )
            continue
        try:
            catalog = pofile.read(path)
        except pofile.PoError as exc:
            errors.append(str(exc))
            continue
        if not catalog.header_value("Language"):
            errors.append("%s: missing Language header" % rel)
        for msgid in catalog.duplicates:
            errors.append("%s: duplicate text %r" % (rel, msgid[:60]))
        for entry in catalog.entries:
            for problem in pofile.problems(entry):
                errors.append("%s:%s: %s" % (rel, entry.line, problem))
        catalogs[path] = catalog
    return catalogs


def check_completeness(data, languages, catalogs, errors, warnings):
    groups = data.get("module_groups") or []
    summary = {}
    for component, pot in components():
        template = pofile.read(pot)
        expected = [entry.msgid for entry in template.entries]
        for language in languages:
            code = language["code"]
            path = pot.parent / ("%s.po" % code)
            rel = path.relative_to(ROOT)
            catalog = catalogs.get(path)
            if catalog is None:
                (errors if language["status"] == "required" else warnings).append(
                    "%s: missing; run scripts/i18n/sync_po.py" % rel
                )
                translated = 0
            else:
                if [entry.msgid for entry in catalog.entries] != expected:
                    warnings.append(
                        "%s: out of step with its template; run scripts/i18n/sync_po.py"
                        % rel
                    )
                by_id = catalog.by_msgid()
                translated = sum(
                    1 for msgid in expected if by_id.get(msgid) and by_id[msgid].msgstr
                )
            missing = len(expected) - translated
            if missing and language["status"] == "required":
                errors.append(
                    "%s: %s untranslated text(s); %s is required" % (rel, missing, code)
                )
            group = (
                "Glossary" if component == "glossary" else group_of(component, groups)
            )
            total = summary.setdefault((code, group), [0, 0])
            total[0] += translated
            total[1] += len(expected)
    return summary


def check_messages(errors):
    for path in sorted(ROOT.glob("sports_federation_*/controllers/*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                value = keyword.value
                if (
                    keyword.arg in MESSAGE_KEYWORDS
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                    and value.value.strip()
                ):
                    errors.append(
                        "%s:%s: %s=%r is shown to users untranslated; use request.env._(...)"
                        % (
                            path.relative_to(ROOT),
                            value.lineno,
                            keyword.arg,
                            value.value[:50],
                        )
                    )


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    data, languages = load_registry(errors)
    catalogs = check_po_files(languages, errors, warnings)
    summary = check_completeness(data, languages, catalogs, errors, warnings)
    check_messages(errors)

    if summary:
        print("Translation completeness:")
        status = {language["code"]: language["status"] for language in languages}
        for (code, group), (done, total) in sorted(summary.items()):
            percent = 100.0 * done / total if total else 100.0
            print(
                "  %-3s %-9s %-18s %5d/%-5d %5.1f%%"
                % (code, status[code], group, done, total, percent)
            )
    else:
        print("No translation templates yet; run scripts/i18n/export_pot.sh.")
    for warning in warnings:
        print("warning: %s" % warning)
    if errors:
        print("Translation contract failed:")
        for error in errors:
            print("- %s" % error)
        return 1
    print("Translation contract passed for %s language(s)." % len(languages))
    return 0


if __name__ == "__main__":
    sys.exit(main())
