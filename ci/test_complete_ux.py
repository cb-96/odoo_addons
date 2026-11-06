"""Executable UX policies and controller-method tests; not browser qualification."""

import base64
from datetime import datetime
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import unittest
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cards = load("ux_cards", "sports_federation_portal/journey_cards.py")
scope = load("ux_scope", "sports_federation_portal/context_scope.py")
time = load("ux_time", "sports_federation_calendar/time_policy.py")


class UrgencyTests(unittest.TestCase):
    def card(self, key, deadline=None, blocking=False):
        return dict(key=key, deadline=deadline, blocking=blocking)

    def test_overdue_precedes_newer_work(self):
        groups = {
            "now": [
                self.card("new", datetime(2026, 12, 1)),
                self.card("old", datetime(2026, 11, 1)),
            ]
        }
        self.assertEqual(
            cards.actionable_cards(groups, datetime(2026, 11, 3))[0]["key"], "old"
        )

    def test_blocking_precedes_nonurgent(self):
        groups = {
            "now": [
                self.card("normal", datetime(2026, 11, 4)),
                self.card("blocked", blocking=True),
            ]
        }
        self.assertEqual(
            cards.actionable_cards(groups, datetime(2026, 11, 3))[0]["key"], "blocked"
        )

    def test_due_soon_and_distant_work_share_list(self):
        groups = {
            "now": [self.card("later", datetime(2026, 12, 1))],
            "soon": [self.card("soon", datetime(2026, 11, 4))],
        }
        self.assertEqual(
            [c["key"] for c in cards.actionable_cards(groups, datetime(2026, 11, 3))],
            ["soon", "later"],
        )

    def test_waiting_and_completed_are_not_actionable(self):
        self.assertEqual(
            cards.actionable_cards(
                {"waiting": [self.card("wait")], "recent": [self.card("done")]}
            ),
            [],
        )

    def test_deadline_strings_and_missing_dates(self):
        groups = {"now": [self.card("none"), self.card("dated", "2026-11-04 10:00:00")]}
        self.assertEqual(
            cards.actionable_cards(groups, datetime(2026, 11, 3))[0]["key"], "dated"
        )

    def test_ties_are_deterministic(self):
        groups = {"now": [self.card("b"), self.card("a")]}
        self.assertEqual([c["key"] for c in cards.actionable_cards(groups)], ["a", "b"])


class ContextTests(unittest.TestCase):
    def test_valid_ids(self):
        self.assertEqual(scope.positive_id("12"), 12)
        self.assertIsNone(scope.positive_id(""))

    def test_invalid_ids(self):
        for value in ("-1", "0", "1.0", "abc", True, "１２"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                scope.positive_id(value)

    def test_context_is_carried(self):
        self.assertEqual(
            scope.scoped_url("/my/rosters", 1, 2, 3),
            "/my/rosters?club=1&team=2&registration=3",
        )

    def test_existing_query_preserved(self):
        self.assertIn(
            "filterby=upcoming",
            scope.scoped_url("/my/match-sheets?filterby=upcoming", 1),
        )

    def test_external_destination_rejected(self):
        for value in (
            "https://example.test/my/work",
            "//example.test/my/work",
            "/odoo",
            "/my/work#x",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                scope.scoped_url(value, 1)


class EventDisplayTests(unittest.TestCase):
    def test_winter_event_time(self):
        self.assertEqual(
            time.utc_to_local("2026-11-03 09:00:00", "Europe/Brussels").hour, 10
        )

    def test_summer_event_time(self):
        self.assertEqual(
            time.utc_to_local("2026-07-03 08:00:00", "Europe/Brussels").hour, 10
        )

    def test_offset_instant(self):
        self.assertEqual(
            time.utc_to_local("2026-11-03T09:00:00+00:00", "Europe/Brussels").hour, 10
        )

    def test_no_value(self):
        self.assertIsNone(time.utc_to_local(False))


class LayoutTests(unittest.TestCase):
    def tree(self, path):
        return etree.parse(str(ROOT / path))

    def test_preparation_has_one_primary_requirement(self):
        tree = self.tree(
            "sports_federation_portal/views/preparation_journey_templates.xml"
        )
        section = tree.xpath('//section[@t-foreach="rows"]')[0]
        self.assertEqual(len(section.xpath('.//a[contains(@class,"btn-primary")]')), 1)
        self.assertTrue(
            section.xpath(".//details//t[@t-foreach=\"row['participation_checks']\"]")
        )

    def test_completed_requirements_are_not_opened(self):
        tree = self.tree(
            "sports_federation_portal/views/preparation_journey_templates.xml"
        )
        node = tree.xpath("//details[@t-att-open]")[0]
        self.assertEqual(node.get("t-att-open"), "requirement == row['next_check']")

    def test_one_visible_task_group(self):
        tree = self.tree("sports_federation_portal/views/role_journey_templates.xml")
        self.assertEqual(len(tree.xpath('//section[@data-journey-bucket="now"]')), 1)
        self.assertFalse(tree.xpath('//section[@data-journey-bucket="soon"]'))

    def test_visual_grid_precedes_settings(self):
        tree = self.tree("sports_federation_live_workspace/static/src/workspaces.xml")
        grid = tree.xpath("//*[@data-visual-timeline]")[0]
        settings = tree.xpath("//*[@data-planning-settings]")[0]
        self.assertIs(grid.getparent(), settings.getparent())
        self.assertLess(
            grid.getparent().index(grid), settings.getparent().index(settings)
        )
        self.assertNotIn("open", settings.attrib)

    def test_selected_fixture_issues_near_grid(self):
        tree = self.tree("sports_federation_live_workspace/static/src/workspaces.xml")
        self.assertTrue(
            tree.xpath(
                '//*[@data-visual-timeline]//*[@aria-label="Selected fixture issues"]'
            )
        )

    def test_planner_error_has_retry(self):
        tree = self.tree(
            "sports_federation_setup_flow/static/src/competition_planner/planner.xml"
        )
        self.assertTrue(
            tree.xpath('//section[@role="alert"]//button[@t-on-click="load"]')
        )

    def test_primary_issue_not_repeated_in_list(self):
        text = (
            ROOT / "sports_federation_setup_flow/models/planner_projection.py"
        ).read_text()
        self.assertIn('issue.get("key") != primary_action.get("key")', text)

    def test_context_filter_precedes_pagination(self):
        for path in ("roster_portal.py", "match_portal.py"):
            text = (ROOT / "sports_federation_portal/controllers" / path).read_text()
            scope_call = re.search(r"_journey_list_scope\s*\(\s*kw", text)
            total_assignment = re.search(r"\btotal\s*=", text)
            self.assertIsNotNone(scope_call)
            self.assertIsNotNone(total_assignment)
            self.assertLess(scope_call.start(), total_assignment.start())
            self.assertIn("url_args=context_query", text)

    def test_historical_review_preserves_instants(self):
        text = (ROOT / "sports_federation_calendar/models/matchday.py").read_text()
        method = text[
            text.index("    def _review_event_timezone") : text.index(
                "    event_timezone ="
            )
        ]
        self.assertNotIn("start_datetime", method)
        self.assertIn("FOR UPDATE", method)
        self.assertRegex(method, r"""self\.check_access\(['"]write['"]\)""")

    def test_public_clock_has_event_timezone(self):
        text = (
            ROOT / "sports_federation_public_site/static/src/js/public_live_board.js"
        ).read_text()
        self.assertIn("timeZone: clock.dataset.eventTimezone", text)

    def test_public_context_has_no_undefined_board_variable(self):
        text = (
            ROOT
            / "sports_federation_public_site/views/website_competition_templates.xml"
        ).read_text()
        self.assertNotIn("board.get('timezone'", text)


@unittest.skipUnless(shutil.which("node"), "Node.js required")
class PlannerBehaviorTests(unittest.TestCase):
    def test_load_failure_retry_and_action_lock(self):
        source = (
            ROOT
            / "sports_federation_setup_flow/static/src/competition_planner/planner.js"
        ).read_text()
        source = re.sub(r"^import .*?;\n", "", source, flags=re.M)
        source = (
            "const Component=class {}; const _t=x=>x; const registry={category:()=>({add:()=>{}})};\n"
            + source
        )
        url = (
            "data:text/javascript;base64," + base64.b64encode(source.encode()).decode()
        )
        code = """import assert from 'node:assert/strict';
const {CompetitionPlanner} = await import(URL);
const p=Object.create(CompetitionPlanner.prototype);
p.editionId=1; p.state={loading:false,data:null,error:'',busy:false};
p.notification={add:()=>{}}; p.action={doAction:async()=>{}};
p.orm={call:async()=>{throw new Error('offline')}};
await p.load(); assert.equal(p.state.loading,false); assert.ok(p.state.error); assert.equal(p.state.data,null);
p.state.data={old:true}; await p.load(); assert.equal(p.state.data.old,true);
let calls=0; p.orm={call:async()=>{calls++;return {fresh:true}}};
await p.doPlannerAction('action'); assert.equal(calls,0);
await p.load(); assert.equal(p.state.error,''); assert.equal(p.state.data.fresh,true);
p.state.busy=true; await p.doPlannerAction('action'); assert.equal(calls,1);
p.state.busy=false; await p.doPlannerAction('action'); assert.equal(calls,2);
""".replace("URL", repr(url))
        result = subprocess.run(
            ["node", "--input-type=module", "-e", code], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_visual_stale_data_blocks_actions_until_retry(self):
        source = (
            ROOT / "sports_federation_live_workspace/static/src/workspaces.js"
        ).read_text()
        source = re.sub(r"^import .*?;\n", "", source, flags=re.M)
        source = (
            "const Component=class {}; const _t=x=>x; const registry={category:()=>({add:()=>{}})};\n"
            + source
        )
        url = (
            "data:text/javascript;base64," + base64.b64encode(source.encode()).decode()
        )
        code = """import assert from 'node:assert/strict';
const {VisualPlan} = await import(URL);
const p=Object.create(VisualPlan.prototype);
p.id=1; p.state={busy:false,error:'',stale:false,data:{old:true},preview:null};
p.orm={call:async()=>{throw new Error('offline')}};
await p.refresh(); assert.equal(p.state.stale,true); assert.equal(p.state.data.old,true);
let ran=false; await p.run(async()=>{ran=true}); assert.equal(ran,false);
p.orm={call:async()=>({fresh:true})}; await p.refresh();
assert.equal(p.state.stale,false); assert.equal(p.state.error,''); assert.equal(p.state.data.fresh,true);
await p.run(async()=>{ran=true}); assert.equal(ran,true);
""".replace("URL", repr(url))
        result = subprocess.run(
            ["node", "--input-type=module", "-e", code], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
