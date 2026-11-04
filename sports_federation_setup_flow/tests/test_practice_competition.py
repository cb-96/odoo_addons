from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_setup_flow")
class TestPracticeCompetition(TransactionCase):
    def _create(self, **values):
        wizard = self.env["federation.practice.competition.wizard"].create(
            dict(
                {
                    "name": "Unit practice",
                    "division_count": 2,
                    "teams_per_division": 4,
                    "gameday_count": 3,
                    "first_gameday_today": False,
                },
                **values,
            )
        )
        wizard.action_create()
        return self.env["federation.competition.edition"].search(
            [("name", "=", "[Practice] %s" % wizard.name)], limit=1
        )

    def test_generator_builds_a_complete_competition_with_a_checklist(self):
        edition = self._create()
        self.assertTrue(edition.is_practice)
        self.assertEqual(len(edition.tournament_ids), 2)
        self.assertEqual(len(edition.practice_club_ids), 4)
        days = self.env["federation.matchday"].search([("edition_id", "=", edition.id)])
        self.assertEqual(len(days), 3)
        fix_items = edition.activity_ids.filtered(lambda a: (a.summary or "").split(". ", 1)[-1].startswith("Fix:"))
        self.assertFalse(fix_items, fix_items.mapped("note"))
        schedules = self.env["federation.schedule"].search([("edition_id", "=", edition.id)])
        self.assertTrue(schedules)
        self.assertTrue(all(schedule.state == "published" for schedule in schedules))
        activities = self.env["mail.activity"].search(
            [("user_id", "=", self.env.user.id), ("summary", "ilike", ". ")]
        )
        self.assertGreaterEqual(len(activities), 9)

    def test_practice_competition_cannot_be_published_on_the_website(self):
        edition = self._create(division_count=1, gameday_count=1)
        with self.assertRaises(ValidationError):
            edition.write({"website_published": True})
        with self.assertRaises(ValidationError):
            edition.tournament_ids.write({"website_published": True})

    def test_remove_archives_competition_and_unused_sample_clubs(self):
        edition = self._create(division_count=1, gameday_count=1)
        clubs = edition.practice_club_ids
        edition.action_remove_practice_competition()
        self.assertFalse(edition.active)
        self.assertFalse(any(clubs.mapped("active")))
        self.assertFalse(edition.activity_ids)

    def test_real_competitions_cannot_be_removed_as_practice(self):
        edition = self._create(division_count=1, gameday_count=1)
        real = edition.copy({"name": "Real copy"})
        with self.assertRaises(ValidationError):
            real.action_remove_practice_competition()
