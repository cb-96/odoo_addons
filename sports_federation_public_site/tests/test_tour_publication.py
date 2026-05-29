"""Tour T-09: Public Site — Tournament Publication and Editorial Scheduling

Walks the public site publication workflow:
  1. Create a tournament and publish it (website_published = True)
  2. Create an editorial item in draft
  3. Schedule the item → 'scheduled'
  4. Publish the item → 'published'
  5. Archive the item → 'archived'
  6. Reset to draft → 'draft'
  7. Verify get_live_items() returns only published/in-window items

Key invariants verified:
- editorial item states: draft → scheduled → published → archived → draft
- get_live_items() excludes draft and archived items
- tournament website_published field is settable
"""

from odoo.tests.common import TransactionCase


class TestTourPublication(TransactionCase):
    """T-09: Public site publication lifecycle tour."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.season = cls.env["federation.season"].create(
            {
                "name": "Publication Tour Season",
                "code": "PUB26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Publication Tour Cup",
                "season_id": cls.season.id,
                "date_start": "2026-06-01",
            }
        )

    def test_publication_lifecycle(self):
        """Tournament publication + editorial item state machine."""

        # STEP 1: Publish tournament
        self.assertFalse(self.tournament.website_published)
        self.tournament.website_published = True
        self.assertTrue(self.tournament.website_published)

        # STEP 2: Create an editorial item in draft
        item = self.env["federation.public.editorial.item"].create(
            {
                "name": "Tour Launch Announcement",
                "summary": "The Tour Cup 2026 is now open!",
                "content_type": "announcement",
                "publish_start": "2026-01-01 09:00:00",
                "season_id": self.season.id,
                "tournament_id": self.tournament.id,
            }
        )
        self.assertEqual(item.publication_state, "draft")
        self.assertFalse(item.can_access_publicly())

        # STEP 3: Schedule the item
        item.action_schedule()
        self.assertEqual(item.publication_state, "scheduled")

        # STEP 4: Publish
        item.action_publish()
        self.assertEqual(item.publication_state, "published")
        self.assertTrue(item.can_access_publicly())

        # STEP 5: get_live_items returns published item
        live = self.env["federation.public.editorial.item"].get_live_items(
            season=self.season
        )
        self.assertIn(item, live)

        # STEP 6: Archive — removed from live feed
        item.action_archive_item()
        self.assertEqual(item.publication_state, "archived")
        self.assertFalse(item.can_access_publicly())

        live_after_archive = self.env[
            "federation.public.editorial.item"
        ].get_live_items(season=self.season)
        self.assertNotIn(item, live_after_archive)

        # STEP 7: Reset to draft
        item.action_reset_to_draft()
        self.assertEqual(item.publication_state, "draft")

        # STEP 8: Second item — publish directly from draft (skip scheduled)
        item2 = self.env["federation.public.editorial.item"].create(
            {
                "name": "Direct Publish Item",
                "summary": "Published directly without scheduling.",
                "content_type": "highlight",
                "season_id": self.season.id,
            }
        )
        item2.action_publish()
        self.assertEqual(item2.publication_state, "published")
