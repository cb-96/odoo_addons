from odoo.tests import TransactionCase


class TestPlayerArchive(TransactionCase):
    """Tests for player archive and restore behaviour."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create({"name": "Archive Test Club"})
        cls.season = cls.env["federation.season"].create({
            "name": "Archive Season 2024",
            "date_start": "2024-09-01",
            "date_end": "2025-06-30",
        })

    def _make_player(self, first="Arch", last="Test", **kwargs):
        vals = {"first_name": first, "last_name": last, "club_id": self.club.id}
        vals.update(kwargs)
        return self.env["federation.player"].create(vals)

    def test_player_can_be_archived(self):
        player = self._make_player()
        self.assertTrue(player.active)
        player.active = False
        self.assertFalse(player.active)

    def test_player_can_be_restored(self):
        player = self._make_player(active=False)
        self.assertFalse(player.active)
        player.active = True
        self.assertTrue(player.active)

    def test_archived_player_not_in_default_search(self):
        """Archived players should not appear in default domain searches."""
        player = self._make_player(first="Hidden", last="Archived")
        player.active = False
        results = self.env["federation.player"].search(
            [("last_name", "=", "Archived")]
        )
        self.assertNotIn(player, results)

    def test_restored_player_appears_in_search(self):
        player = self._make_player(first="Visible", last="Restored", active=False)
        player.active = True
        results = self.env["federation.player"].search(
            [("last_name", "=", "Restored")]
        )
        self.assertIn(player, results)

    def test_is_eligible_follows_active_license(self):
        """Eligibility is driven by active licenses, not archive status."""
        player = self._make_player(first="Elig", last="Arch")
        lic = self.env["federation.player.license"].create({
            "name": "ARCH-LIC-001",
            "player_id": player.id,
            "season_id": self.season.id,
            "club_id": self.club.id,
            "issue_date": "2024-09-01",
            "expiry_date": "2025-06-30",
            "state": "active",
        })
        self.assertTrue(player.is_eligible)
        lic.action_cancel()
        self.assertFalse(player.is_eligible)
