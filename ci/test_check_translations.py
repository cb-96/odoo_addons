"""Tests for ci/check_translations.py and the PO tooling; no Odoo required."""

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "i18n"))
import pofile  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "check_translations", ROOT / "ci" / "check_translations.py"
)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
spec = importlib.util.spec_from_file_location(
    "sync_po", ROOT / "scripts" / "i18n" / "sync_po.py"
)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def catalog(language, pairs):
    return pofile.Catalog(
        header=pofile.Entry(msgid="", msgstr=pofile.header_text(language, "m")),
        entries=[pofile.Entry(msgid=a, msgstr=b) for a, b in pairs],
    )


class TranslationContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "i18n").mkdir()
        self.module = self.root / "sports_federation_demo_mod"
        (self.module / "i18n").mkdir(parents=True)
        (self.module / "controllers").mkdir()
        self.registry({"nl": "draft"})
        pofile.write(
            catalog("", [("Hello %(name)s", ""), ("<b>Bold</b> text", "")]),
            self.module / "i18n" / "sports_federation_demo_mod.pot",
        )
        for module in (check, sync):
            module.ROOT = self.root
            module.REGISTRY = self.root / "i18n" / "languages.json"

    def tearDown(self):
        self.tmp.cleanup()

    def registry(self, statuses):
        data = {
            "languages": [
                {"code": code, "odoo_codes": ["%s_BE" % code], "status": status}
                for code, status in statuses.items()
            ],
            "module_groups": [{"name": "All", "modules": "*"}],
        }
        (self.root / "i18n" / "languages.json").write_text(json.dumps(data))

    def run_check(self):
        with redirect_stdout(io.StringIO()) as out:
            code = check.main()
        return code, out.getvalue()

    def test_good_translation_passes(self):
        pofile.write(
            catalog(
                "nl",
                [
                    ("Hello %(name)s", "Hallo %(name)s"),
                    ("<b>Bold</b> text", "<b>Vet</b>gedrukt"),
                ],
            ),
            self.module / "i18n" / "nl.po",
        )
        code, out = self.run_check()
        self.assertEqual(code, 0, out)
        self.assertIn("100.0%", out)

    def test_broken_placeholder_and_markup_fail(self):
        pofile.write(
            catalog("nl", [("Hello %(name)s", "Hallo"), ("<b>Bold</b> text", "Vet")]),
            self.module / "i18n" / "nl.po",
        )
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("placeholders differ", out)
        self.assertIn("markup differs", out)

    def test_unregistered_language_fails(self):
        pofile.write(catalog("es", []), self.module / "i18n" / "es.po")
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("'es' is not in i18n/languages.json", out)

    def test_required_language_must_be_complete(self):
        self.registry({"nl": "required"})
        pofile.write(
            catalog(
                "nl", [("Hello %(name)s", "Hallo %(name)s"), ("<b>Bold</b> text", "")]
            ),
            self.module / "i18n" / "nl.po",
        )
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("1 untranslated", out)

    def test_untranslatable_portal_message_fails(self):
        (self.module / "controllers" / "main.py").write_text(
            "def route(self):\n    return self._redirect_with_query('/my', success='Saved')\n"
        )
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("success='Saved'", out)
        (self.module / "controllers" / "main.py").write_text(
            "def route(self):\n    return self._redirect_with_query('/my', success=request.env._('Saved'))\n"
        )
        self.assertEqual(self.run_check()[0], 0)

    def test_adding_a_language_creates_and_syncs_files(self):
        self.registry({"nl": "draft", "de": "draft"})
        pofile.write(
            catalog(
                "nl", [("<b>Bold</b> text", "<b>Vet</b>gedrukt"), ("Removed", "Weg")]
            ),
            self.module / "i18n" / "nl.po",
        )
        with redirect_stdout(io.StringIO()):
            sys.argv = ["sync_po.py"]
            self.assertEqual(sync.main(), 0)
        german = pofile.read(self.module / "i18n" / "de.po")
        self.assertEqual(
            [e.msgid for e in german.entries], ["Hello %(name)s", "<b>Bold</b> text"]
        )
        self.assertEqual(german.header_value("Language"), "de")
        dutch = pofile.read(self.module / "i18n" / "nl.po").by_msgid()
        self.assertNotIn("Removed", dutch)
        self.assertEqual(dutch["<b>Bold</b> text"].msgstr, "<b>Vet</b>gedrukt")


if __name__ == "__main__":
    unittest.main()
