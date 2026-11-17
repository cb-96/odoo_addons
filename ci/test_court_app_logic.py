"""Offline court app: server rules, device commands, and parity with the phone.

The shared cases in ``ci/fixtures/court_scoring_cases.json`` run through the
server policy here and through the phone's ``policy.js`` in
``ci/js/test_court_app.mjs`` (run below when Node.js is available).
"""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "court_policy", ROOT / "sports_federation_live_workspace/policy.py"
)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

CASES = json.loads((ROOT / "ci/fixtures/court_scoring_cases.json").read_text())["cases"]


class TestScoringParity(unittest.TestCase):
    def test_server_agrees_with_shared_cases(self):
        for case in CASES:
            with self.subTest(case=case["name"]):

                def call(case=case):
                    return p.validate_capture(
                        case["payload"],
                        case["mode"],
                        case["set_target"],
                        case["max_periods"],
                        complete=case["complete"],
                        win_points=case["set_points"][0],
                        draw_points=case["set_points"][1],
                    )

                if case["valid"]:
                    call()
                else:
                    with self.assertRaises(ValueError):
                        call()

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_phone_logic(self):
        result = subprocess.run(
            ["node", "--test", str(ROOT / "ci/js/test_court_app.mjs")],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode, 0, result.stdout[-4000:] + result.stderr[-2000:]
        )


def command(**values):
    base = {
        "key": "k" * 10,
        "revision": 0,
        "operation": "save",
        "payload": {"home": 0, "away": 0},
        "signature": "s" * 64,
    }
    base.update(values)
    return base


class TestDeviceCommands(unittest.TestCase):
    def test_confirmation_is_split_off_the_receipt(self):
        cmd, extra = p.validate_device_command(
            command(operation="submit", confirmation={"method": "pin", "pin": "4821"})
        )
        self.assertNotIn("confirmation", cmd)
        self.assertEqual(extra["confirmation"], {"method": "pin", "pin": "4821"})

    def test_confirmation_only_on_submit(self):
        with self.assertRaises(ValueError):
            p.validate_device_command(command(confirmation={"method": "self"}))

    def test_pin_format(self):
        for pin in ("12", "1234567", "12a4", 1234):
            with self.subTest(pin=pin), self.assertRaises(ValueError):
                p.validate_confirmation({"method": "pin", "pin": pin})

    def test_side_commands(self):
        cmd, extra = p.validate_device_command(
            {"key": "x" * 12, "operation": "log", "payload": {"events": []}}
        )
        self.assertEqual(cmd["operation"], "log")
        self.assertEqual(extra, {})
        with self.assertRaises(ValueError):
            p.validate_device_command(
                {"key": "x" * 12, "operation": "log", "payload": {}, "revision": 1}
            )
        with self.assertRaises(ValueError):
            p.validate_device_command(command(operation="delete"))

    def test_participation(self):
        self.assertEqual(
            p.validate_participation({"sheets": {"12": [5, 3]}}), {12: [3, 5]}
        )
        for payload in (
            {"sheets": {}},
            {"sheets": {"x": []}},
            {"sheets": {"1": [3, 3]}},
            {"sheets": {"1": ["3"]}},
            {"other": 1},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                p.validate_participation(payload)

    def test_match_log(self):
        events = p.validate_match_log(
            {
                "events": [
                    {"type": "card_blue", "side": "home", "player_id": 4, "set": 3},
                    {"type": "timeout", "side": "away", "half": 2},
                ]
            }
        )
        self.assertEqual(events[0]["player_id"], 4)
        self.assertIsNone(events[1]["player_id"])
        for event in (
            {"type": "card_red", "side": "home"},
            {"type": "timeout", "side": "away", "player_id": 3},
            {"type": "timeout", "side": "away", "half": 3},
            {"type": "goal", "side": "home"},
        ):
            with self.subTest(event=event), self.assertRaises(ValueError):
                p.validate_match_log({"events": [event]})


if __name__ == "__main__":
    unittest.main()
