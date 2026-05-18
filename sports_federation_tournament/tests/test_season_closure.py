"""Tests for season closure checklist: action_close blocks while tournaments are active."""
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestSeasonClosure(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Closure Test Season",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.season.action_open()

    # ── helpers ──────────────────────────────────────────────────────────────

    def _make_tournament(self, season=None, **kwargs):
        vals = {
            "name": "Test Tournament",
            "season_id": (season or self.season).id,
            "date_start": "2026-01-15",
        }
        vals.update(kwargs)
        return self.env["federation.tournament"].create(vals)

    # ── blocking tests ───────────────────────────────────────────────────────

    def test_close_blocked_by_draft_tournament(self):
        """Season cannot be closed when a tournament is in draft state."""
        self._make_tournament(name="Draft Tournament")
        with self.assertRaises(ValidationError) as cm:
            self.season.action_close()
        self.assertIn("Draft Tournament", str(cm.exception))

    def test_close_blocked_by_open_tournament(self):
        """Season cannot be closed when a tournament is open."""
        t = self._make_tournament(name="Open Tournament")
        t.write({"state": "open"})
        with self.assertRaises(ValidationError):
            self.season.action_close()

    def test_close_blocked_by_in_progress_tournament(self):
        """Season cannot be closed when a tournament is in progress."""
        t = self._make_tournament(name="In Progress Tournament")
        t.write({"state": "in_progress"})
        with self.assertRaises(ValidationError):
            self.season.action_close()

    # ── passing tests ────────────────────────────────────────────────────────

    def test_close_allowed_with_no_tournaments(self):
        """Season with no tournaments can be closed directly."""
        empty_season = self.env["federation.season"].create(
            {
                "name": "Empty Season",
                "date_start": "2027-01-01",
                "date_end": "2027-12-31",
            }
        )
        empty_season.action_open()
        empty_season.action_close()
        self.assertEqual(empty_season.state, "closed")

    def test_close_allowed_when_all_tournaments_closed(self):
        """Season can be closed once all tournaments are closed."""
        season = self.env["federation.season"].create(
            {
                "name": "All Closed Season",
                "date_start": "2028-01-01",
                "date_end": "2028-12-31",
            }
        )
        season.action_open()
        t = self._make_tournament(season=season, name="Closed T")
        t.write({"state": "closed"})
        season.action_close()
        self.assertEqual(season.state, "closed")

    def test_close_allowed_when_all_tournaments_cancelled(self):
        """Season can be closed once all tournaments are cancelled."""
        season = self.env["federation.season"].create(
            {
                "name": "All Cancelled Season",
                "date_start": "2029-01-01",
                "date_end": "2029-12-31",
            }
        )
        season.action_open()
        t = self._make_tournament(season=season, name="Cancelled T")
        t.action_cancel()
        season.action_close()
        self.assertEqual(season.state, "closed")

    def test_close_allowed_mixed_closed_and_cancelled(self):
        """Season can be closed when some tournaments are closed and others cancelled."""
        season = self.env["federation.season"].create(
            {
                "name": "Mixed Terminal Season",
                "date_start": "2030-01-01",
                "date_end": "2030-12-31",
            }
        )
        season.action_open()
        t1 = self._make_tournament(season=season, name="T Closed")
        t2 = self._make_tournament(season=season, name="T Cancelled")
        t1.write({"state": "closed"})
        t2.action_cancel()
        season.action_close()
        self.assertEqual(season.state, "closed")
