from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError
from datetime import date, timedelta


class TestClubRepresentative(TransactionCase):
    """Tests for club representative model and role types."""

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        # Create a club
        cls.club = cls.env["federation.club"].create({"name": "Test Club"})
        cls.user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Club Representative Test User",
                    "login": "club.representative.test.user@example.com",
                    "email": "club.representative.test.user@example.com",
                }
            )
        )
        # Create partners
        cls.partner1 = cls.env["res.partner"].create({"name": "John Doe"})
        cls.partner2 = cls.env["res.partner"].create({"name": "Jane Smith"})
        cls.partner3 = cls.env["res.partner"].create({"name": "Bob Johnson"})
        # Get role types (created by data file)
        cls.role_competition = cls.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )
        cls.role_finance = cls.env.ref(
            "sports_federation_portal.role_type_finance_contact"
        )
        cls.role_safeguarding = cls.env.ref(
            "sports_federation_portal.role_type_safeguarding_contact"
        )
        cls.role_president = cls.env.ref("sports_federation_portal.role_type_president")
        cls.role_other = cls.env.ref("sports_federation_portal.role_type_other")

    def test_create_multiple_representatives(self):
        """Test creating multiple representatives for one club."""
        rep1 = self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": self.partner1.id,
                "role_type_id": self.role_competition.id,
                "is_primary": True,
                "date_start": "2025-01-01",
            }
        )
        rep2 = self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": self.partner2.id,
                "role_type_id": self.role_finance.id,
                "is_primary": True,
                "date_start": "2025-01-01",
            }
        )
        self.assertEqual(len(self.club.representative_ids), 2)
        self.assertIn(rep1, self.club.representative_ids)
        self.assertIn(rep2, self.club.representative_ids)

    def test_role_type_linkage(self):
        """Test that representative correctly links to role type."""
        rep = self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": self.partner1.id,
                "role_type_id": self.role_competition.id,
            }
        )
        self.assertEqual(rep.role_type_id, self.role_competition)
        self.assertTrue(rep.role_type_id.is_competition_contact)
        self.assertFalse(rep.role_type_id.is_finance_contact)

    def test_primary_contact_uniqueness(self):
        """Test that only one primary representative per role type per club."""
        self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": self.partner1.id,
                "role_type_id": self.role_competition.id,
                "is_primary": True,
            }
        )
        # Attempt to create another primary for same role type should fail
        with self.assertRaises(ValidationError):
            self.env["federation.club.representative"].create(
                {
                    "club_id": self.club.id,
                    "partner_id": self.partner2.id,
                    "role_type_id": self.role_competition.id,
                    "is_primary": True,
                }
            )

    def test_multiple_primaries_different_roles(self):
        """Test that different role types can each have a primary."""
        rep1 = self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": self.partner1.id,
                "role_type_id": self.role_competition.id,
                "is_primary": True,
            }
        )
        rep2 = self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": self.partner2.id,
                "role_type_id": self.role_finance.id,
                "is_primary": True,
            }
        )
        self.assertTrue(rep1.is_primary)
        self.assertTrue(rep2.is_primary)

    def test_is_current_computation(self):
        """Test is_current computed field."""
        # Active representative with no dates
        rep = self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": self.partner1.id,
                "role_type_id": self.role_competition.id,
            }
        )
        self.assertTrue(rep.is_current)

        # Representative with start date in future
        rep.date_start = date.today() + timedelta(days=30)
        rep._compute_is_current()
        self.assertFalse(rep.is_current)

        # Representative with end date in past
        rep.date_start = date.today() - timedelta(days=60)
        rep.date_end = date.today() - timedelta(days=1)
        rep._compute_is_current()
        self.assertFalse(rep.is_current)

        # Representative with valid date range
        rep.date_start = date.today() - timedelta(days=30)
        rep.date_end = date.today() + timedelta(days=30)
        rep._compute_is_current()
        self.assertTrue(rep.is_current)

    def test_date_validation(self):
        """Test that start date cannot be after end date."""
        with self.assertRaises(ValidationError):
            self.env["federation.club.representative"].create(
                {
                    "club_id": self.club.id,
                    "partner_id": self.partner1.id,
                    "role_type_id": self.role_competition.id,
                    "date_start": "2025-12-31",
                    "date_end": "2025-01-01",
                }
            )

    def test_partner_club_role_uniqueness(self):
        """Test that a partner can only have one representative per club and role."""
        self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": self.partner1.id,
                "role_type_id": self.role_competition.id,
            }
        )
        # Same partner, same club, same role should fail
        with self.assertRaises(Exception):
            self.env["federation.club.representative"].create(
                {
                    "club_id": self.club.id,
                    "partner_id": self.partner1.id,
                    "role_type_id": self.role_competition.id,
                }
            )

    def test_get_club_for_user(self):
        """Test _get_club_for_user helper method."""
        # No representative yet
        club = self.env["federation.club.representative"]._get_club_for_user(self.user)
        self.assertFalse(club)

        # Create representative linked to user
        self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": self.user.partner_id.id,
                "user_id": self.user.id,
                "role_type_id": self.role_competition.id,
            }
        )
        club = self.env["federation.club.representative"]._get_club_for_user(self.user)
        self.assertEqual(club, self.club)

    def test_get_clubs_for_user(self):
        """Test _get_clubs_for_user helper method."""
        club2 = self.env["federation.club"].create({"name": "Test Club 2"})

        self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": self.user.partner_id.id,
                "user_id": self.user.id,
                "role_type_id": self.role_competition.id,
            }
        )
        self.env["federation.club.representative"].create(
            {
                "club_id": club2.id,
                "partner_id": self.user.partner_id.id,
                "user_id": self.user.id,
                "role_type_id": self.role_finance.id,
            }
        )
        clubs = self.env["federation.club.representative"]._get_clubs_for_user(
            self.user
        )
        self.assertEqual(len(clubs), 2)
        self.assertIn(self.club, clubs)
        self.assertIn(club2, clubs)

    def test_scope_helpers_return_empty_for_non_club_portal_user(self):
        """Test that scope helpers return empty for non-club portal user."""
        official_group = self.env.ref(
            "sports_federation_portal.group_federation_portal_official"
        )
        official_user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Non Club Portal User",
                    "login": "non.club.portal.user@example.com",
                    "email": "non.club.portal.user@example.com",
                    "group_ids": [(6, 0, [official_group.id])],
                }
            )
        )

        clubs = (
            self.env["federation.club.representative"]
            .with_user(official_user)
            ._get_clubs_for_user()
        )
        club_scope = (
            self.env["federation.club.representative"]
            .with_user(official_user)
            ._get_club_scope_for_user()
        )

        self.assertFalse(clubs)
        self.assertFalse(club_scope)

    def test_get_primary_contact(self):
        """Test _get_primary_contact helper method."""
        rep = self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": self.partner1.id,
                "role_type_id": self.role_competition.id,
                "is_primary": True,
            }
        )
        primary = self.env["federation.club.representative"]._get_primary_contact(
            self.club, "competition_contact"
        )
        self.assertEqual(primary, rep)

        # Non-primary should not be returned
        self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": self.partner2.id,
                "role_type_id": self.role_finance.id,
                "is_primary": False,
            }
        )
        primary = self.env["federation.club.representative"]._get_primary_contact(
            self.club, "finance_contact"
        )
        self.assertFalse(primary)

    def test_role_type_get_by_code(self):
        """Test role type get_by_code helper method."""
        role = self.env["federation.club.role.type"].get_by_code("competition_contact")
        self.assertEqual(role, self.role_competition)

        role = self.env["federation.club.role.type"].get_by_code("nonexistent")
        self.assertFalse(role)

    def test_partner_representative_count(self):
        """Test partner representative count computation."""
        self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": self.partner1.id,
                "role_type_id": self.role_competition.id,
            }
        )
        club2 = self.env["federation.club"].create({"name": "Test Club 2"})
        self.env["federation.club.representative"].create(
            {
                "club_id": club2.id,
                "partner_id": self.partner1.id,
                "role_type_id": self.role_finance.id,
            }
        )
        self.assertEqual(self.partner1.federation_representative_count, 2)

    def test_user_represented_clubs(self):
        """Test user represented_club_ids computation."""
        self.env["federation.club.representative"].create(
            {
                "club_id": self.club.id,
                "partner_id": self.user.partner_id.id,
                "user_id": self.user.id,
                "role_type_id": self.role_competition.id,
            }
        )
        self.assertIn(self.club, self.user.represented_club_ids)
