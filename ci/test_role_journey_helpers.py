"""Pure-helper tests; no Odoo runtime required or simulated product qualification."""
import importlib.util
from pathlib import Path
import unittest

FILE = Path(__file__).resolve().parents[1] / "sports_federation_portal/journey_navigation.py"
spec = importlib.util.spec_from_file_location("journey_navigation", FILE)
nav = importlib.util.module_from_spec(spec); spec.loader.exec_module(nav)

class JourneyHelpers(unittest.TestCase):
    def test_known_destinations(self):
        for path in ("/my/rosters/1", "/my/competition-entries/23", "/my/work/registrations/12", "/my/players/3/parental-approvals"):
            self.assertTrue(nav.safe_destination(path), path)
    def test_external_destinations_rejected(self):
        for path in ("https://example.com", "//example.com/my/rosters/1", "/my/rosters/1?next=https://example.com", "/my/rosters/1#evil", "/my/rosters/%2e%2e", "/my/rosters/1\\evil", "/my/rosters/0", "/my/rosters/-1", "/my/rosters/1\n"):
            self.assertFalse(nav.safe_destination(path), path)
    def test_unknown_return_key(self): self.assertEqual(nav.return_url("https://example.com"), "/my/action-items")
    def test_return_filters_allowlisted(self):
        result = nav.return_url("club", {"scope": "club", "status": "recent", "redirect": "https://example.com", "task_type": "invalid"})
        self.assertEqual(result, "/my/action-items?scope=club&status=recent")
    def test_official_return_preserves_only_allowed_filter(self):
        result = nav.return_url("official", {"filterby": "history", "page": "9", "redirect": "//evil.test"})
        self.assertEqual(result, "/my/referee-assignments?filterby=history")
    def test_submitted_entry_waits(self): self.assertEqual(nav.presentation("open", "club", "federation.competition.entry", "submitted"), ("waiting", "federation"))
    def test_draft_entry_actionable(self): self.assertEqual(nav.presentation("open", "club", "federation.competition.entry", "draft"), ("actionable", "club"))
    def test_submitted_sheet_waits(self): self.assertEqual(nav.presentation("open", "club", "federation.match.sheet", "submitted")[0], "waiting")
    def test_pending_consent_waits(self): self.assertEqual(nav.presentation("open", "club", "federation.team.roster.line", "present", True)[0], "waiting")
    def test_completed_source(self): self.assertEqual(nav.presentation("done", "club", "missing", None), ("completed", "none"))
    def test_unknown_source(self): self.assertEqual(nav.presentation("open", "club", "missing", None), ("unavailable", "unknown"))
    def test_manager_actor(self): self.assertEqual(nav.presentation("open", "manager", "federation.match", "present"), ("actionable", "federation"))
    def test_acknowledged_not_complete(self): self.assertEqual(nav.presentation("acknowledged", "club", "federation.team", "present")[0], "actionable")

if __name__ == "__main__": unittest.main()
