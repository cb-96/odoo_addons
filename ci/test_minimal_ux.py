"""Source and pure-policy checks; not browser or novice acceptance evidence."""

from datetime import datetime
import ast
import importlib.util
from pathlib import Path
import unittest
import base64
import shutil
import subprocess
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "event_time", ROOT / "sports_federation_calendar/time_policy.py"
)
time_policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(time_policy)


class EventTimeTests(unittest.TestCase):
    def test_winter(self):
        self.assertEqual(
            time_policy.local_to_utc("2026-11-03T10:00", "Europe/Brussels"),
            datetime(2026, 11, 3, 9),
        )

    def test_summer(self):
        self.assertEqual(
            time_policy.local_to_utc("2026-07-03T10:00", "Europe/Brussels"),
            datetime(2026, 7, 3, 8),
        )

    def test_utc(self):
        self.assertEqual(
            time_policy.local_to_utc("2026-11-03T10:00", "UTC"),
            datetime(2026, 11, 3, 10),
        )

    @unittest.skipUnless(
        shutil.which("node"), "Node.js required for browser-time formatting policy"
    )
    def test_javascript_event_time_ignores_browser_timezone(self):
        source = (
            ROOT / "sports_federation_live_workspace/static/src/visual_helpers.js"
        ).read_bytes()
        url = "data:text/javascript;base64," + base64.b64encode(source).decode()
        code = """import assert from 'node:assert/strict';
const {formatEventTime} = await import(URL);
assert.match(formatEventTime('2026-11-03 09:00:00', 'Europe/Brussels', 'en-GB'), /10:00/);
assert.match(formatEventTime('2026-07-03 08:00:00', 'Europe/Brussels', 'en-GB'), /10:00/);
assert.match(formatEventTime('2026-11-03T09:00:00Z', 'Europe/Brussels', 'en-GB'), /10:00/);
assert.equal(formatEventTime(false), '');
assert.equal(formatEventTime('invalid'), '');
""".replace("URL", repr(url))
        import os

        for timezone in ("Pacific/Honolulu", "Asia/Tokyo"):
            result = subprocess.run(
                ["node", "--input-type=module", "-e", code],
                env=dict(os.environ, TZ=timezone),
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing(self):
        self.assertIsNone(time_policy.local_to_utc(False, "UTC"))

    def test_invalid(self):
        for value, zone in [
            ("invalid", "UTC"),
            ("2026-11-03T10:00+01:00", "Europe/Brussels"),
            ("2026-11-03T10:00", "invalid"),
            ("2026-03-29T02:30", "Europe/Brussels"),
            ("2026-10-25T02:30", "Europe/Brussels"),
        ]:
            with self.subTest(value=value, zone=zone), self.assertRaises(ValueError):
                time_policy.local_to_utc(value, zone)


class MinimalLayoutTests(unittest.TestCase):
    def tree(self, path):
        return etree.parse(str(ROOT / path))

    def test_waiting_and_history_collapsed(self):
        tree = self.tree("sports_federation_portal/views/role_journey_templates.xml")
        group = tree.xpath('//template[@id="connected_work_groups"]')[0]
        details = group.xpath(".//details[@t-att-data-journey-bucket]")
        self.assertTrue(details)
        self.assertTrue(all("open" not in node.attrib for node in details))

    def test_card_has_one_action_and_disclosed_delegation(self):
        tree = self.tree("sports_federation_portal/views/role_journey_templates.xml")
        card = tree.xpath('//template[@id="connected_work_card"]')[0]
        self.assertEqual(len(card.xpath(".//a[@data-journey-open]")), 1)
        self.assertTrue(
            card.xpath(
                './/details//form[@action="/my/action-items/assign"]//input[@name="csrf_token"]'
            )
        )

    def test_role_sections_replace_the_role_switcher(self):
        """The overview shows one section per role; there is no role picker."""
        journeys = self.tree(
            "sports_federation_portal/views/role_journey_templates.xml"
        )
        self.assertFalse(journeys.xpath('//select[@id="journey-role"]'))
        overview = self.tree("sports_federation_portal/views/portal_templates.xml")
        sections = overview.xpath(
            "//div[@t-if and section[@t-att-data-overview-section]]"
        )
        self.assertEqual(len(sections), 1)
        self.assertIn("overview.get('sections')", sections[0].get("t-if"))

    def test_one_promoted_planner_action(self):
        tree = self.tree(
            "sports_federation_setup_flow/static/src/competition_planner/planner.xml"
        )
        self.assertEqual(len(tree.xpath('//button[contains(@class,"btn-primary")]')), 1)
        self.assertTrue(tree.xpath('//details//button[@t-on-click="openAdvanced"]'))

    def test_court_recovery_disclosed_but_conflict_visible(self):
        tree = self.tree("sports_federation_live_workspace/static/src/workspaces.xml")
        court = tree.xpath('//t[@t-name="sports_federation_live_workspace.Court"]')[0]
        self.assertTrue(court.xpath('.//details//button[@t-on-click="exportEvidence"]'))
        self.assertTrue(court.xpath('.//div[@t-if="state.conflict"]'))
        self.assertTrue(
            court.xpath('.//button[@t-on-click="sync"][@t-if="state.pending.length"]')
        )

    def test_timezone_field_is_on_form_only(self):
        tree = self.tree("sports_federation_calendar/views/calendar_views.xml")
        self.assertEqual(len(tree.xpath('//form//field[@name="event_timezone"]')), 1)
        self.assertFalse(tree.xpath('//list//field[@name="event_timezone"]'))

    def test_assets_exist(self):
        for module in ("base", "calendar", "portal", "setup_flow", "live_workspace"):
            manifest = ast.literal_eval(
                (ROOT / ("sports_federation_" + module) / "__manifest__.py").read_text()
            )
            for paths in manifest.get("assets", {}).values():
                for path in paths:
                    if isinstance(path, str) and "*" not in path:
                        self.assertTrue((ROOT / path).exists(), path)


if __name__ == "__main__":
    unittest.main()
