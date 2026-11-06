from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_app")
class TestWebsitePublication(TransactionCase):
    def _competition(self):
        wizard = self.env["federation.practice.competition.wizard"].create(
            {
                "name": "Website %s" % self.id(),
                "division_count": 2,
                "teams_per_division": 4,
                "gameday_count": 2,
                "first_gameday_today": False,
                "first_gameday": fields.Date.context_today(self.env.user)
                + timedelta(days=30),
            }
        )
        wizard.action_create()
        edition = self.env["federation.competition.edition"].search(
            [("name", "=", "[Practice] %s" % wizard.name)], limit=1
        )
        # Turn the sample into a real competition to exercise publication.
        edition.write({"is_practice": False})
        return edition

    def test_publish_website_publishes_the_competition_and_ready_divisions(self):
        edition = self._competition()
        self.assertFalse(edition.public_slug)
        edition.action_publish_website()
        self.assertTrue(edition.website_published)
        self.assertTrue(edition.public_slug)
        self.assertTrue(all(edition.tournament_ids.mapped("website_published")))
        edition.action_unpublish_website()
        self.assertFalse(any(edition.tournament_ids.mapped("website_published")))

    def test_publish_website_explains_missing_format(self):
        edition = self._competition()
        self.env["federation.competition.structure"].search(
            [("edition_id", "=", edition.id)]
        ).write({"state": "superseded"})
        edition.tournament_ids.invalidate_recordset()
        with self.assertRaisesRegex(ValidationError, "teams and format"):
            edition.action_publish_website()

    def test_practice_competition_still_cannot_be_published(self):
        edition = self._competition()
        edition.write({"is_practice": True})
        with self.assertRaises(ValidationError):
            edition.action_publish_website()
