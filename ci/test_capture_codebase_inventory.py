import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("capture_codebase_inventory.py")
SPEC = importlib.util.spec_from_file_location("capture_codebase_inventory", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TestCodebaseInventory(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"],
            cwd=self.repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"], cwd=self.repo, check=True
        )
        addon = self.repo / "sports_federation_sample"
        (addon / "controllers").mkdir(parents=True)
        (addon / "data").mkdir()
        (addon / "__manifest__.py").write_text(
            "{'version': '19.0.1.0.0', 'depends': ['base'], 'installable': True}\n"
        )
        (addon / "controllers" / "main.py").write_text(
            "from odoo import http\n"
            "class C(http.Controller):\n"
            "    @http.route('/sample', auth='public', csrf=False, methods=['POST'])\n"
            "    def sample(self):\n"
            "        self.env['x'].sudo().search([])\n"
        )
        (addon / "data" / "cron.xml").write_text(
            '<odoo><record id="cron_sample" model="ir.cron"/></odoo>\n'
        )
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.repo, check=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_inventory_is_deterministic_and_finds_security_surfaces(self):
        first = MODULE.build_inventory(self.repo, large_file_lines=1)
        second = MODULE.build_inventory(self.repo, large_file_lines=1)
        self.assertEqual(first, second)
        self.assertEqual(first["counts"]["addons"], 1)
        self.assertEqual(first["counts"]["routes"], 1)
        self.assertEqual(first["counts"]["sudo_calls"], 1)
        self.assertEqual(first["counts"]["scheduled_jobs"], 1)
        self.assertEqual(first["routes"][0]["auth"], "'public'")
        self.assertEqual(first["routes"][0]["csrf"], "False")

    def test_serialized_inventory_round_trips(self):
        payload = MODULE.build_inventory(self.repo, large_file_lines=100)
        self.assertEqual(json.loads(json.dumps(payload)), payload)


if __name__ == "__main__":
    unittest.main()
