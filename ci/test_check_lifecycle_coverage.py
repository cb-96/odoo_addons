#!/usr/bin/env python3
"""Tests for ci/check_lifecycle_coverage.py."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_lifecycle_coverage as coverage  # noqa: E402

CONTRACT = {
    "schema_version": 1,
    "test": {
        "path": "addon/tests/test_life.py",
        "tag": "sf_competition_lifecycle",
        "required_tags": ["post_install", "sf_competition_lifecycle"],
        "forbidden_patterns": [
            {"pattern": "\\.sudo\\(\\)", "reason": "no elevation"},
            {"pattern": "[\"'](?:state)[\"']\\s*:", "reason": "no state writes"},
        ],
        "required_methods": [{"name": "test_a", "covers": "a"}, {"name": "test_b", "covers": "b"}],
    },
}
GOOD = '''from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_competition_lifecycle")
class TestLife(TransactionCase):
    def test_a(self):
        pass

    def test_b(self):
        pass
'''


class SourceTests(unittest.TestCase):
    def tree(self, text: str, register: bool = True) -> Path:
        root = Path(tempfile.mkdtemp())
        tests = root / "addon" / "tests"
        tests.mkdir(parents=True)
        (tests / "test_life.py").write_text(text, encoding="utf-8")
        (tests / "__init__.py").write_text("from . import test_life\n" if register else "", encoding="utf-8")
        return root

    def test_complete_source_passes(self):
        self.assertEqual(coverage.check_source(CONTRACT, self.tree(GOOD)), [])

    def test_missing_file_is_reported(self):
        root = Path(tempfile.mkdtemp())
        self.assertIn("missing", coverage.check_source(CONTRACT, root)[0])

    def test_missing_method_and_tag_are_reported(self):
        text = GOOD.replace("def test_b", "def helper").replace(', "sf_competition_lifecycle"', "")
        errors = coverage.check_source(CONTRACT, self.tree(text))
        self.assertTrue(any("missing required test test_b" in e for e in errors))
        self.assertTrue(any("lacks tags" in e for e in errors))

    def test_shortcuts_are_reported(self):
        text = GOOD.replace("pass", 'self.env["x"].sudo().write({"state": "done"})', 1)
        errors = coverage.check_source(CONTRACT, self.tree(text))
        self.assertTrue(any("no elevation" in e for e in errors))
        self.assertTrue(any("no state writes" in e for e in errors))

    def test_unregistered_module_is_reported(self):
        errors = coverage.check_source(CONTRACT, self.tree(GOOD, register=False))
        self.assertTrue(any("does not import" in e for e in errors))


class LogTests(unittest.TestCase):
    def log(self, text: str) -> Path:
        path = Path(tempfile.mkdtemp()) / "odoo.log"
        path.write_text(text, encoding="utf-8")
        return path

    def test_all_started_and_clean_result_passes(self):
        text = (
            "INFO db odoo.addons.addon.tests.test_life: Starting TestLife.test_a ...\n"
            "INFO db odoo.addons.addon.tests.test_life: Starting TestLife.test_b ...\n"
            "INFO db odoo.tests.result: 0 failed, 0 error(s) of 2 tests when loading database 'db'\n"
        )
        self.assertEqual(coverage.check_log(CONTRACT, self.log(text)), [])

    def test_tag_selecting_nothing_fails(self):
        text = "INFO db odoo.tests.result: 0 failed, 0 error(s) of 0 tests when loading database 'db'\n"
        errors = coverage.check_log(CONTRACT, self.log(text))
        self.assertIn("test_a: did not run", errors)

    def test_failure_is_reported(self):
        text = (
            "Starting TestLife.test_a ...\nStarting TestLife.test_b ...\n"
            "ERROR db odoo.addons.addon.tests.test_life: FAIL: TestLife.test_b\n"
            "odoo.tests.result: 1 failed, 0 error(s) of 2 tests\n"
        )
        errors = coverage.check_log(CONTRACT, self.log(text))
        self.assertIn("test_b: failed", errors)
        self.assertTrue(any("1 failed" in e for e in errors))

    def test_repository_contract_is_valid(self):
        contract = coverage.load_contract()
        names = [m["name"] for m in contract["test"]["required_methods"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(name.startswith("test_") for name in names))


if __name__ == "__main__":
    unittest.main()
