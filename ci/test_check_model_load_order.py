import importlib.util
import tempfile
import textwrap
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_model_load_order", Path(__file__).with_name("check_model_load_order.py")
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class ModelLoadOrderTests(unittest.TestCase):
    def addon(self, root, name, depends, files):
        (root / name).mkdir()
        (root / name / "__manifest__.py").write_text(repr({"depends": depends}))
        for relative, source in files.items():
            path = root / name / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(source))

    def base(self, root):
        self.addon(
            root,
            "sf_base",
            [],
            {
                "__init__.py": "from . import models\n",
                "models/__init__.py": "from . import thing\n",
                "models/thing.py": """
                    class Thing:
                        _name = "sf.thing"
                """,
            },
        )

    def test_extension_before_definition_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(
                root,
                "sf_late",
                [],
                {
                    "__init__.py": "from . import models\nfrom . import services\n",
                    "models/__init__.py": "from . import ext\n",
                    "models/ext.py": """
                        class Ext:
                            _inherit = "sf.commands"
                    """,
                    "services/__init__.py": "from . import commands\n",
                    "services/commands.py": """
                        class Commands:
                            _name = "sf.commands"
                    """,
                },
            )
            errors = checker.check(root)
        self.assertEqual(len(errors), 1)
        self.assertIn("before sf_late defines it", errors[0])

    def test_extension_after_definition_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.addon(
                root,
                "sf_ok",
                [],
                {
                    "__init__.py": "from . import services\n",
                    "services/__init__.py": "from . import commands, ext\n",
                    "services/commands.py": """
                        class Commands:
                            _name = "sf.commands"
                    """,
                    "services/ext.py": """
                        class Ext:
                            _inherit = "sf.commands"
                    """,
                },
            )
            self.assertEqual(checker.check(root), [])

    def test_missing_dependency_is_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.base(root)
            self.addon(
                root,
                "sf_ext",
                [],
                {
                    "__init__.py": "from . import ext\n",
                    "ext.py": """
                        class Ext:
                            _inherit = "sf.thing"
                    """,
                },
            )
            errors = checker.check(root)
        self.assertEqual(len(errors), 1)
        self.assertIn("does not depend on", errors[0])

    def test_transitive_dependency_and_core_models_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.base(root)
            self.addon(root, "sf_middle", ["sf_base"], {"__init__.py": ""})
            self.addon(
                root,
                "sf_ext",
                ["sf_middle"],
                {
                    "__init__.py": "from . import ext\n",
                    "ext.py": """
                        class Ext:
                            _inherit = ["sf.thing", "mail.thread"]
                    """,
                },
            )
            self.assertEqual(checker.check(root), [])


if __name__ == "__main__":
    unittest.main()
