import importlib.util
import unittest
from pathlib import Path

CHECK_PATH = Path(__file__).with_name("check_odoo_registry_log.py")
SPEC = importlib.util.spec_from_file_location("check_odoo_registry_log", CHECK_PATH)
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class TestOdooRegistryLog(unittest.TestCase):
    def test_clean_log_passes(self):
        self.assertEqual(
            CHECK.find_registry_failures("Registry loaded.\nModules loaded.\n"), []
        )

    def test_inconsistent_module_state_fails(self):
        failures = CHECK.find_registry_failures(
            "ERROR odoo.modules.loading: Some modules have inconsistent states"
        )
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][0], "inconsistent module states")

    def test_unloadable_model_fails(self):
        failures = CHECK.find_registry_failures(
            "Model federation.match.slot is declared but cannot be loaded!"
        )
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][0], "model declared but not loadable")

    def test_missing_dependency_summary_fails(self):
        failures = CHECK.find_registry_failures(
            "Some modules are not loaded, some dependencies may be missing: ['legacy_addon']"
        )
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][0], "unloaded modules or missing dependencies")


if __name__ == "__main__":
    unittest.main()
