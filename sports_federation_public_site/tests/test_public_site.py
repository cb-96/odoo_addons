from odoo.tests import TransactionCase
from odoo.tools.misc import mute_logger


class TestPublicSite(TransactionCase):
    """Test cases for public site module."""

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        # Create test tournament
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Test Tournament",
                "code": "TT2024",
                "date_start": "2024-01-01",
                "date_end": "2024-01-31",
            }
        )
        # Create test standing
        cls.standing = cls.env["federation.standing"].create(
            {
                "name": "Test Standing",
                "tournament_id": cls.tournament.id,
            }
        )

    def test_unpublished_tournament_not_visible_on_list(self):
        """Test that unpublished tournaments are not shown on list."""
        self.tournament.website_published = False
        # The controller would filter by website_published = True
        tournaments = self.env["federation.tournament"].search(
            [
                ("website_published", "=", True),
            ]
        )
        self.assertNotIn(self.tournament, tournaments)

    def test_published_tournament_visible_on_list(self):
        """Test that published tournaments are shown on list."""
        self.tournament.website_published = True
        tournaments = self.env["federation.tournament"].search(
            [
                ("website_published", "=", True),
            ]
        )
        self.assertIn(self.tournament, tournaments)

    def test_unpublished_tournament_detail_returns_404(self):
        """Test that unpublished tournament detail returns 404."""
        self.tournament.website_published = False
        self.assertFalse(self.tournament.can_access_public_detail())

    def test_published_tournament_detail_renders(self):
        """Test that published tournament detail renders."""
        self.tournament.website_published = True
        self.assertTrue(self.tournament.can_access_public_detail())

    def test_results_visibility_requires_results_toggle(self):
        """Direct results access requires both publish and results flags."""
        self.tournament.website_published = True
        self.tournament.show_public_results = False
        self.assertFalse(self.tournament.can_access_public_results())

        self.tournament.show_public_results = True
        self.assertTrue(self.tournament.can_access_public_results())

    def test_public_results_query_only_returns_approved_matches(self):
        """Test that public results query only returns approved matches."""
        approved_match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": False,
                "away_team_id": False,
                "result_state": "approved",
            }
        )
        submitted_match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": False,
                "away_team_id": False,
                "result_state": "submitted",
            }
        )

        matches = self.env["federation.match"].search(
            [
                ("tournament_id", "=", self.tournament.id),
                ("result_state", "=", "approved"),
            ]
        )
        self.assertIn(approved_match, matches)
        self.assertNotIn(submitted_match, matches)

    def test_standings_visibility_requires_standings_toggle(self):
        """Direct standings access requires both publish and standings flags."""
        self.tournament.website_published = True
        self.tournament.show_public_standings = False
        self.assertFalse(self.tournament.can_access_public_standings())

        self.tournament.show_public_standings = True
        self.assertTrue(self.tournament.can_access_public_standings())

    def test_only_published_standings_visible(self):
        """Test that only published standings are visible."""
        self.tournament.website_published = True
        self.standing.website_published = True
        standings = self.env["federation.standing"].search(
            [
                ("tournament_id", "=", self.tournament.id),
                ("website_published", "=", True),
            ]
        )
        self.assertIn(self.standing, standings)

    def test_unpublished_standing_hidden(self):
        """Test that unpublished standings are hidden."""
        self.tournament.website_published = True
        self.standing.website_published = False
        standings = self.env["federation.standing"].search(
            [
                ("tournament_id", "=", self.tournament.id),
                ("website_published", "=", True),
            ]
        )
        self.assertNotIn(self.standing, standings)

    def test_tournament_public_fields(self):
        """Test that tournament public fields are set correctly."""
        self.tournament.website_published = True
        self.tournament.public_description = "Test description"
        self.tournament.public_slug = "test-slug"
        self.tournament.public_featured = True
        self.tournament.public_editorial_summary = "Front-page summary"
        self.tournament.public_pinned_announcement = "Pinned note"
        self.tournament.show_public_results = True
        self.tournament.show_public_standings = True
        self.assertIn("Test description", str(self.tournament.public_description))
        self.assertEqual(self.tournament.public_slug, "test-slug")
        self.assertTrue(self.tournament.public_featured)
        self.assertEqual(self.tournament.public_editorial_summary, "Front-page summary")
        self.assertEqual(self.tournament.public_pinned_announcement, "Pinned note")
        self.assertTrue(self.tournament.show_public_results)
        self.assertTrue(self.tournament.show_public_standings)

    def test_public_site_state_labels_are_humanized(self):
        """Public-facing state labels should read like visitor copy."""
        club = self.env["federation.club"].create({"name": "Label Club"})
        home_team = self.env["federation.team"].create(
            {
                "name": "Label Home",
                "club_id": club.id,
                "code": "PLH",
            }
        )
        away_team = self.env["federation.team"].create(
            {
                "name": "Label Away",
                "club_id": club.id,
                "code": "PLA",
            }
        )
        participant = self.env["federation.tournament.participant"].create(
            {
                "tournament_id": self.tournament.id,
                "team_id": home_team.id,
                "state": "confirmed",
            }
        )
        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": home_team.id,
                "away_team_id": away_team.id,
                "state": "done",
            }
        )

        self.tournament.state = "open"

        self.assertEqual(
            self.tournament.get_public_site_state_label(), "Open for entries"
        )
        self.assertEqual(participant.get_public_site_state_label(), "Confirmed")
        self.assertEqual(match.get_public_site_state_label(), "Final")

    def test_public_slug_must_be_unique(self):
        """Test that public slug must be unique."""
        self.tournament.public_slug = "shared-slug"
        with self.assertRaises(Exception), mute_logger(
            "odoo.sql_db"
        ), self.cr.savepoint():
            self.env["federation.tournament"].create(
                {
                    "name": "Other Tournament",
                    "code": "OTHER-TT",
                    "date_start": "2024-02-01",
                    "date_end": "2024-02-28",
                    "public_slug": "shared-slug",
                }
            )

    def test_menu_cleanup_rehomes_legacy_competitions_menu(self):
        """Test that menu cleanup rehomes legacy competitions menu."""
        website = self.env["website"].search([], limit=1)
        root_menu = self.env["website.menu"].create(
            {
                "name": "Top Menu Cleanup Root",
                "url": "#",
                "website_id": website.id,
            }
        )
        tournament_menu = self.env["website.menu"].create(
            {
                "name": "Tournaments",
                "url": "/tournaments",
                "parent_id": root_menu.id,
                "sequence": 50,
                "website_id": website.id,
            }
        )
        legacy_menu = self.env["website.menu"].create(
            {
                "name": "Competitions",
                "url": "/competitions",
                "parent_id": root_menu.id,
                "sequence": 55,
                "is_visible": True,
                "website_id": website.id,
            }
        )

        self.env["website.menu"]._cleanup_stale_public_site_menus()

        legacy_menu = self.env["website.menu"].browse(legacy_menu.id)
        self.assertEqual(legacy_menu.parent_id, tournament_menu)
        self.assertEqual(legacy_menu.name, "Tournament Updates")
        self.assertEqual(legacy_menu.url, "/tournaments#published")
        self.assertTrue(legacy_menu.is_visible)
        self.assertEqual(legacy_menu.sequence, 10)

    def test_menu_cleanup_hides_duplicate_legacy_entries(self):
        """Test that menu cleanup hides duplicate legacy entries."""
        website = self.env["website"].search([], limit=1)
        root_menu = self.env["website.menu"].create(
            {
                "name": "Top Menu Cleanup Duplicate Root",
                "url": "#",
                "website_id": website.id,
            }
        )
        tournament_menu = self.env["website.menu"].create(
            {
                "name": "Tournaments",
                "url": "/tournaments",
                "parent_id": root_menu.id,
                "sequence": 50,
                "website_id": website.id,
            }
        )
        published_menu = self.env["website.menu"].create(
            {
                "name": "Tournament Updates",
                "url": "/tournaments#published",
                "parent_id": tournament_menu.id,
                "sequence": 10,
                "is_visible": True,
                "website_id": website.id,
            }
        )
        legacy_sibling = self.env["website.menu"].create(
            {
                "name": "Competitions",
                "url": "/competitions",
                "parent_id": root_menu.id,
                "sequence": 55,
                "is_visible": True,
                "website_id": website.id,
            }
        )
        legacy_child = self.env["website.menu"].create(
            {
                "name": "Competition Archive",
                "url": "/competitions/archive",
                "parent_id": tournament_menu.id,
                "sequence": 15,
                "is_visible": True,
                "website_id": website.id,
            }
        )

        self.env["website.menu"]._cleanup_stale_public_site_menus()

        published_menu = self.env["website.menu"].browse(published_menu.id)
        self.assertEqual(published_menu.parent_id, tournament_menu)
        self.assertEqual(published_menu.name, "Tournament Updates")
        self.assertEqual(published_menu.url, "/tournaments#published")
        self.assertTrue(published_menu.is_visible)
        self.assertFalse(legacy_sibling.exists())
        self.assertFalse(legacy_child.exists())

    def test_website_cleanup_rebrands_placeholder_shell_and_footer(self):
        """Test that website cleanup rebrands placeholder shell and footer."""
        website = self.env["website"].search([], limit=1)
        footer_view = (
            self.env["ir.ui.view"]
            .sudo()
            .search(
                [
                    ("website_id", "=", website.id),
                    ("key", "=", "website.template_footer_descriptive"),
                ],
                limit=1,
            )
        )
        placeholder_footer_arch = (
            '<data inherit_id="website.layout" name="Descriptive" active="True">'
            '<xpath expr="//div[@id=\'footer\']" position="replace">'
            '<div id="footer">Designed for companies</div>'
            "</xpath>"
            "</data>"
        )

        website.write({"name": "My Website"})
        website.company_id.write(
            {
                "name": "YourCompany",
                "phone": "+1 555-555-5556",
                "street": "8000 Marina Blvd, Suite 300",
                "city": "Brisbane",
                "zip": "94005",
            }
        )
        if footer_view:
            footer_view.write({"arch_db": placeholder_footer_arch})

        summary = website._cleanup_default_public_site_content()

        website = self.env["website"].browse(website.id)
        company = website.company_id
        footer_view = (
            self.env["ir.ui.view"]
            .sudo()
            .search(
                [
                    ("website_id", "=", website.id),
                    ("key", "=", "website.template_footer_descriptive"),
                ],
                limit=1,
            )
        )

        self.assertEqual(website.name, "Sports Federation")
        self.assertEqual(company.name, "Sports Federation")
        self.assertFalse(company.phone)
        self.assertFalse(company.street)
        self.assertFalse(company.city)
        self.assertFalse(company.zip)
        self.assertTrue(footer_view)
        self.assertEqual(summary["branding_renamed"], 1)
        self.assertEqual(summary["company_records_cleaned"], 1)
        self.assertEqual(summary["footers_cleaned"], 1)
        self.assertIn("Sports Federation", footer_view.arch_db)
        self.assertIn(
            "Tournament hubs, schedules, results, standings", footer_view.arch_db
        )
        self.assertNotIn("Designed for companies", footer_view.arch_db)

    def test_website_cleanup_removes_placeholder_navigation_entries(self):
        """Test that website cleanup removes placeholder website navigation entries."""
        website = self.env["website"].search([], limit=1)
        root_menu = website.menu_id

        events_menu = self.env["website.menu"].create(
            {
                "name": "Events",
                "url": "/event",
                "parent_id": root_menu.id,
                "sequence": 20,
                "website_id": website.id,
            }
        )
        news_menu = self.env["website.menu"].create(
            {
                "name": "News",
                "url": "/blog/3",
                "parent_id": root_menu.id,
                "sequence": 30,
                "website_id": website.id,
            }
        )
        about_menu = self.env["website.menu"].create(
            {
                "name": "About Us",
                "url": "/about-us",
                "parent_id": root_menu.id,
                "sequence": 40,
                "website_id": website.id,
            }
        )
        contact_menu = self.env["website.menu"].create(
            {
                "name": "Contact us",
                "url": "/contactus",
                "parent_id": root_menu.id,
                "sequence": 60,
                "website_id": website.id,
            }
        )

        summary = website._cleanup_default_public_site_content()

        self.assertFalse(events_menu.exists())
        self.assertFalse(news_menu.exists())
        self.assertFalse(about_menu.exists())
        self.assertFalse(contact_menu.exists())
        self.assertGreaterEqual(summary["menus_removed"], 4)

    def test_standing_public_fields(self):
        """Test that standing public fields are set correctly."""
        self.standing.website_published = True
        self.standing.public_title = "Public Title"
        self.assertEqual(self.standing.public_title, "Public Title")
