#!/usr/bin/env python3
"""Validate the federation-wide readiness vocabulary contract.

The check keeps three promises:

* user-facing readiness surfaces speak the six shared words and no longer use
  the legacy variants;
* every detailed internal state of the mapped models has a shared status, so a
  new state can never silently fall outside the vocabulary;
* "can this game day run?" is answered by exactly one service, extended by one
  provider per component, and every consumer calls that service.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "ci/contracts/readiness_vocabulary.json"
BLOCKER_KEYWORDS = {"key", "status", "problem", "action", "destination"}
errors: list[str] = []


def load_vocabulary(relative):
    spec = importlib.util.spec_from_file_location(
        "readiness_vocabulary", ROOT / relative
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selection_codes(path, class_name, field_name):
    """Return the codes of a Selection field or list constant, else ``None``."""
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == class_name):
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            names = [t.id for t in statement.targets if isinstance(t, ast.Name)]
            if field_name not in names:
                continue
            value = statement.value
            if isinstance(value, ast.Call) and value.args:
                value = value.args[0]
            if isinstance(value, ast.List):
                return {
                    element.elts[0].value
                    for element in value.elts
                    if isinstance(element, ast.Tuple)
                    and isinstance(element.elts[0], ast.Constant)
                }
    return None


def check_labels(vocabulary, contract):
    labels = [label for _code, label in vocabulary.SELECTION]
    if labels != contract["labels"]:
        errors.append("The vocabulary must define exactly %s." % contract["labels"])
    for status in vocabulary.STATUSES:
        for table in (vocabulary.LABELS, vocabulary.BADGE_CLASSES):
            if status not in table:
                errors.append("Status %r has no label or badge." % status)
    if set(vocabulary.LEGACY_LABELS) & set(labels):
        errors.append("A legacy label is part of the vocabulary.")


def check_surfaces(vocabulary, contract):
    words = sorted(vocabulary.LEGACY_LABELS)
    for relative in contract["surfaces"]:
        path = ROOT / relative
        if not path.is_file():
            errors.append("Readiness surface %s is missing." % relative)
            continue
        text = path.read_text(encoding="utf-8")
        for word in words:
            if re.search(r"(?<![A-Za-z])%s(?![A-Za-z])" % re.escape(word), text):
                errors.append(
                    "%s uses the legacy readiness wording %r." % (relative, word)
                )
        if re.search(r"""(['">])Waiting(['"<])""", text):
            errors.append("%s uses the legacy readiness wording 'Waiting'." % relative)


def check_state_domains(vocabulary, contract):
    for item in contract["state_domains"]:
        codes = selection_codes(item["path"], item["class"], item["field"])
        if codes is None:
            errors.append(
                "Cannot read %s.%s in %s."
                % (item["class"], item["field"], item["path"])
            )
            continue
        mapped = set(vocabulary.STATE_MAPPINGS.get(item["domain"], {}))
        for code in sorted(codes - mapped):
            errors.append(
                "State %r of %s.%s has no readiness mapping (%s)."
                % (code, item["class"], item["field"], item["domain"])
            )


def python_files():
    for module in sorted(ROOT.glob("sports_federation_*")):
        if not module.is_dir():
            continue
        for path in module.rglob("*.py"):
            if "tests" in path.parts or "__pycache__" in path.parts:
                continue
            yield path


def check_service(contract):
    owners = []
    for path in python_files():
        text = path.read_text(encoding="utf-8")
        pattern = r'^\s+_name = "%s"' % re.escape(contract["service"]["model"])
        if re.search(pattern, text, re.M):
            owners.append(path.relative_to(ROOT).as_posix())
    if owners != [contract["service"]["owner"]]:
        errors.append(
            "%s must be defined once, in %s; found %s."
            % (contract["service"]["model"], contract["service"]["owner"], owners)
        )


def check_providers(vocabulary, contract):
    declared = set(contract["providers"])
    if declared != set(vocabulary.COMPONENT_ORDER):
        errors.append("Provider contract and COMPONENT_ORDER disagree.")
    for key, relative in contract["providers"].items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        needle = '("%s", "_readiness_%s")' % (key, key)
        if needle not in text:
            errors.append("%s does not register the %r provider." % (relative, key))


def check_consumers(contract):
    for name, item in contract["consumers"].items():
        path = ROOT / item["path"]
        if not path.is_file():
            errors.append("Consumer %s (%s) is missing." % (name, item["path"]))
            continue
        text = path.read_text(encoding="utf-8")
        for token in item["tokens"]:
            if token not in text:
                errors.append(
                    "Consumer %s lacks %r in %s." % (name, token, item["path"])
                )


def check_blockers():
    for path in python_files():
        if path.name == "readiness_vocabulary.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", "")
            )
            if name != "make_blocker":
                continue
            given = {keyword.arg for keyword in node.keywords}
            missing = BLOCKER_KEYWORDS - given
            if missing:
                errors.append(
                    "%s:%s make_blocker lacks %s."
                    % (path.relative_to(ROOT), node.lineno, sorted(missing))
                )


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if contract.get("schema_version") != 1:
        errors.append("Readiness vocabulary contract schema_version must be 1.")
    vocabulary = load_vocabulary(contract["vocabulary_module"])
    check_labels(vocabulary, contract)
    check_surfaces(vocabulary, contract)
    check_state_domains(vocabulary, contract)
    check_service(contract)
    check_providers(vocabulary, contract)
    check_consumers(contract)
    check_blockers()
    if errors:
        print("Readiness vocabulary contract failed:")
        for error in errors:
            print("- %s" % error)
        return 1
    print("Readiness vocabulary contract passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
