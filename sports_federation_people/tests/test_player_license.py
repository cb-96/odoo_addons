from odoo.tests import TransactionCase
from odoo.exceptions import ValidationError


class TestPlayerLicense(TransactionCase):
    """Tests for federation.player.license lifecycle, constraints, and eligibility."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create({"name": "License Test Club"})
        cls.season = cls.env["federation.season"].create({
            "name": "License Season 2024",
            "date_start": "2024-09-01",
            "date_end": "2025-06-30",
        })
        cls.season2 = cls.env["federation.season"].create({
            "name": "License Season 2025",
            "date_start": "2025-09-01",
            "date_end": "2026-06-30",
        })
        cls.player = cls.env["federation.player"].create({
            "first_name": "LicTest",
            "last_name": "Player",
            "club_id": cls.club.id,
        })

    def _make_license(self, player=None, season=None, name="LIC-001", **kwargs):
        vals = {
            "name": name,
            "player_id": (player or self.player).id,
            "season_id": (season or self.season).id,
            "club_id": self.club.id,
            "issue_date": "2024-09-01",
            "expiry_date": "2025-06-30",
        }
        vals.update(kwargs)
        return self.env["federation.player.license"].create(vals)

    def test_new_license_is_draft(self):
        lic = self._make_license()
        self.assertEqual(lic.state, "draft")

    def test_activate_transitions_to_active(self):
        lic = self._make_license()
        lic.action_activate()
        self.assertEqual(lic.state, "active")

    def test_cancel_from_active(self):
        lic = self._make_license()
        lic.action_activate()
        lic.action_cancel()
        self.assertEqual(lic.state, "cancelled")

    def test_draft_resets_from_active(self):
        lic = self._make_license()
        lic.action_activate()
        lic.action_draft()
        self.assertEqual(lic.state, "draft")

    def test_is_eligible_true_with_active_license(self):
        lic = self._make_license()
        lic.action_activate()
        self.assertTrue(self.player.is_eligible)

    def test_is_eligible_false_with_only_draft_license(self):
        self._make_license()
        self.assertFalse(self.player.is_eligible)

    def test_is_eligible_false_after_cancel(self):
        lic = self._make_license()
        lic.action_activate()
        lic.action_cancel()
        self.assertFalse(self.player.is_eligible)

    def test_duplicate_license_same_player_same_season_blocked(self):
        self._make_license(name="LIC-DUP-001")
        with self.assertRaises(Exception):
            # Same player + same season → unique constraint violation
            self._make_license(name="LIC-DUP-002")

    def test_license_different_season_allowed(self):
        self._make_license(season=self.season, name="LIC-S1")
        lic2 = self._make_license(season=self.season2, name="LIC-S2")
        self.assertTrue(lic2.id)

    def test_expiry_before_issue_raises(self):
        with self.assertRaises(ValidationError):
            self._make_license(
                issue_date="2024-09-01",
                expiry_date="2024-08-01",
            )

    def test_expiry_equal_to_issue_raises(self):
        with self.assertRaises(ValidationError):
            self._make_license(
                issue_date="2024-09-01",
                expiry_date="2024-09-01",
            )
