import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


privileged = load("privileged_quality", "ci/check_privileged_inventory_quality.py")


def test_privileged_inventory_rejects_vague_reason(tmp_path):
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps([{
        "file": "controller.py",
        "function": "write",
        "statement": "record.sudo()",
        "reason": "needed",
    }]))
    assert privileged.violations(inventory)


def test_privileged_inventory_accepts_scoped_reason(tmp_path):
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps([{
        "file": "controller.py",
        "function": "write",
        "statement": "record.sudo()",
        "reason": "ownership scope checked before elevation",
    }]))
    assert privileged.violations(inventory) == []
