"""Dependency-light contracts for local full CI and repair integration."""

import importlib.util
import json
import re
import tempfile
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[2]


class Loader(yaml.SafeLoader):
    pass


Loader.yaml_implicit_resolvers = {
    k: [v for v in vs if v[0] != "tag:yaml.org,2002:bool"]
    for k, vs in Loader.yaml_implicit_resolvers.items()
}

Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|false|True|False|TRUE|FALSE)$"),
    list("tTfF"),
)


def addon_directories(root):
    """Ignore leftover directories that are not addon source trees."""
    return {
        manifest.parent.name
        for manifest in root.glob("sports_federation_*/__manifest__.py")
        if manifest.is_file()
    }


class LocalCIContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.load(
            (ROOT / ".github/workflows/ci-local.yml").read_text(), Loader=Loader
        )
        cls.config = json.loads((ROOT / "ci/local/repair/controller.json").read_text())

    def test_trusted_pushes_only(self):
        self.assertEqual(set(self.workflow["on"]), {"push", "workflow_dispatch"})
        self.assertEqual(
            self.workflow["on"]["push"]["branches"],
            ["feat/offline-gameday", "autofix/**"],
        )

    def test_all_jobs_guarded_and_local(self):
        for job in self.workflow["jobs"].values():
            self.assertEqual(
                job["runs-on"], ["self-hosted", "linux", "x64", "federation-ci"]
            )
            self.assertIn("github.repository == 'cb-96/odoo_addons'", job["if"])
            self.assertNotIn("schedule", job["if"])

    def test_no_integration_secrets(self):
        text = (ROOT / ".github/workflows/ci-local.yml").read_text()
        self.assertNotIn("secrets.", text)

    def test_every_original_suite_preserved(self):
        original = yaml.load(
            (ROOT / ".github/workflows/ci.yml").read_text(), Loader=Loader
        )
        for name, job in original["jobs"].items():
            actual = self.workflow["jobs"][name]
            self.assertEqual(
                actual.get("strategy", {}).get("matrix"),
                job.get("strategy", {}).get("matrix"),
            )
            expected = [
                s["run"]
                for s in job["steps"]
                if "run" in s and s.get("name") != "Prepare CI environment file"
            ]
            runs = [s["run"] for s in actual["steps"] if "run" in s]
            for command in expected:
                self.assertIn(command, runs)

    def test_full_gate_covers_all_jobs(self):
        jobs = self.workflow["jobs"]
        self.assertEqual(
            set(jobs["full-ci-gate"]["needs"]), set(jobs) - {"full-ci-gate"}
        )
        self.assertIn("!= 'success'", jobs["full-ci-gate"]["steps"][0]["run"])

    def test_matrix_serialized(self):
        for job in self.workflow["jobs"].values():
            if "strategy" in job:
                self.assertEqual(job["strategy"]["max-parallel"], 1)

    def test_checkout_credentials_not_persisted(self):
        for job in self.workflow["jobs"].values():
            for step in job["steps"]:
                if step.get("uses", "").startswith("actions/checkout@"):
                    self.assertIs(step["with"]["persist-credentials"], False)

    def test_review_only_and_real_modules(self):
        self.assertFalse(self.config["publish_enabled"])
        self.assertEqual(self.config["required_workflows"], ["ci-local.yml"])
        modules = addon_directories(ROOT)
        self.assertEqual(set(self.config["allow_prefixes"]), modules)

    def test_addon_discovery_ignores_non_addon_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active = root / "sports_federation_example"
            active.mkdir()
            (active / "__manifest__.py").write_text("{}", encoding="utf-8")
            leftover = root / "sports_federation_unused"
            leftover.mkdir()
            (leftover / "__pycache__").mkdir()
            self.assertEqual(addon_directories(root), {active.name})

    def test_ci_wait_budget(self):
        self.assertGreaterEqual(self.config["ci_seconds"], 8 * 3600)
        self.assertGreater(
            self.config["session_seconds"], 3 * self.config["ci_seconds"]
        )

    def test_worker_protected_paths(self):
        spec = importlib.util.spec_from_file_location(
            "repair_controller", ROOT / "ci/local/repair/controller.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertFalse(module.allowed(".github/workflows/ci-local.yml", self.config))
        self.assertFalse(
            module.allowed("sports_federation_base/AGENTS.md", self.config)
        )
        self.assertTrue(
            module.allowed("sports_federation_base/models/player.py", self.config)
        )


if __name__ == "__main__":
    unittest.main()
