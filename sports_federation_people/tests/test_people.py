"""Tests for sports_federation_people: players and player licenses."""

from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from odoo.tools.misc import mute_logger


class TestFederationPlayer(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "People Test Club",
                "code": "PTC",
            }
        )
        cls.player = cls.env["federation.player"].create(
            {
                "first_name": "John",
                "last_name": "Doe",
                "birth_date": "1995-03-15",
                "gender": "male",
                "club_id": cls.club.id,
            }
        )

    def test_create_player(self):
        """Test that create player."""
        self.assertTrue(self.player.id)
        self.assertEqual(self.player.state, "active")

    def test_computed_name(self):
        """Test that computed name."""
        self.assertEqual(self.player.name, "John Doe")

    def test_future_birth_date_rejected(self):
        """Test that future birth date rejected."""
        with self.assertRaises(ValidationError):
            self.env["federation.player"].create(
                {
                    "first_name": "Future",
                    "last_name": "Player",
                    "birth_date": "2099-01-01",
                }
            )

    def test_player_state_transitions(self):
        """Test that player state transitions."""
        self.player.action_deactivate()
        self.assertEqual(self.player.state, "inactive")
        self.player.action_suspend()
        self.assertEqual(self.player.state, "suspended")
        self.player.action_activate()
        self.assertEqual(self.player.state, "active")

    def test_name_search_by_first_name(self):
        """Test that name search by first name."""
        results = self.env["federation.player"].name_search("John")
        ids = [r[0] if isinstance(r, (list, tuple)) else r.id for r in results]
        self.assertIn(self.player.id, ids)

    def test_name_search_by_last_name(self):
        """Test that name search by last name."""
        results = self.env["federation.player"].name_search("Doe")
        ids = [r[0] if isinstance(r, (list, tuple)) else r.id for r in results]
        self.assertIn(self.player.id, ids)


class TestFederationPlayerLicense(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "License Club",
                "code": "LC",
            }
        )
        cls.player = cls.env["federation.player"].create(
            {
                "first_name": "Jane",
                "last_name": "Smith",
                "club_id": cls.club.id,
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "License Season",
                "code": "LS24",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )

    def test_create_license(self):
        """Test that create license."""
        lic = self.env["federation.player.license"].create(
            {
                "name": "LIC-001",
                "player_id": self.player.id,
                "season_id": self.season.id,
                "club_id": self.club.id,
                "issue_date": "2024-01-15",
                "expiry_date": "2024-12-31",
            }
        )
        self.assertTrue(lic.id)
        self.assertEqual(lic.state, "draft")

    def test_license_invalid_dates(self):
        """Test that license invalid dates."""
        with self.assertRaises(ValidationError):
            self.env["federation.player.license"].create(
                {
                    "name": "LIC-BAD",
                    "player_id": self.player.id,
                    "season_id": self.season.id,
                    "club_id": self.club.id,
                    "issue_date": "2024-06-01",
                    "expiry_date": "2024-01-01",
                }
            )

    def test_license_state_transitions(self):
        """Test that license state transitions."""
        lic = self.env["federation.player.license"].create(
            {
                "name": "LIC-002",
                "player_id": self.player.id,
                "season_id": self.season.id,
                "club_id": self.club.id,
                "issue_date": "2024-01-15",
                "expiry_date": "2024-12-31",
            }
        )
        lic.action_activate()
        self.assertEqual(lic.state, "active")
        lic.action_cancel()
        self.assertEqual(lic.state, "cancelled")
        lic.action_draft()
        self.assertEqual(lic.state, "draft")

    def test_duplicate_player_season_rejected(self):
        """Test that duplicate player season rejected."""
        self.env["federation.player.license"].create(
            {
                "name": "LIC-003",
                "player_id": self.player.id,
                "season_id": self.season.id,
                "club_id": self.club.id,
                "issue_date": "2024-01-15",
                "expiry_date": "2024-12-31",
            }
        )
        with self.assertRaises(Exception), mute_logger("odoo.sql_db"), self.cr.savepoint():
            self.env["federation.player.license"].create(
                {
                    "name": "LIC-004",
                    "player_id": self.player.id,
                    "season_id": self.season.id,
                    "club_id": self.club.id,
                    "issue_date": "2024-02-01",
                    "expiry_date": "2024-12-31",
                }
            )
            self.env.cr.flush()

    def test_license_count_computed(self):
        """Test that license count computed."""
        self.env["federation.player.license"].create(
            {
                "name": "LIC-005",
                "player_id": self.player.id,
                "season_id": self.season.id,
                "club_id": self.club.id,
                "issue_date": "2024-01-15",
                "expiry_date": "2024-12-31",
            }
        )
        self.player.invalidate_recordset()
        self.assertEqual(self.player.license_count, 1)
