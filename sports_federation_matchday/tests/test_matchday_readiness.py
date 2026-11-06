from unittest.mock import patch

from odoo.addons.sports_federation_base import readiness_vocabulary as vocabulary
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_matchday_readiness")
class TestMatchdayReadiness(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        season = cls.env["federation.season"].create(
            {
                "name": "Readiness Season",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Readiness Competition", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Readiness Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        venue = cls.env["federation.venue"].create({"name": "Readiness Venue"})
        cls.matchday = cls.env["federation.matchday"].create(
            {
                "name": "Readiness Game Day",
                "edition_id": cls.edition.id,
                "date": "2026-10-10",
                "venue_id": venue.id,
            }
        )
        cls.service = cls.env["federation.matchday.readiness"]

    def _component(self, result, key):
        return next(item for item in result["components"] if item["key"] == key)

    def test_unpublished_game_day_needs_a_schedule(self):
        result = self.service.evaluate(self.matchday)
        schedule = self._component(result, "schedule")
        self.assertEqual(schedule["status"], vocabulary.ACTION_NEEDED)
        blocker = schedule["blockers"][0]
        self.assertIn("schedule", blocker["problem"].lower())
        self.assertEqual(blocker["destination"]["model"], "federation.matchday")
        self.assertEqual(blocker["destination"]["res_id"], self.matchday.id)
        self.assertEqual(blocker["deadline"], "2026-10-10")
        self.assertFalse(result["can_run"])
        self.assertEqual(result["overall"], vocabulary.ACTION_NEEDED)

    def test_nothing_is_checked_without_matches(self):
        result = self.service.evaluate(self.matchday)
        self.assertEqual(
            self._component(result, "courts")["status"], vocabulary.NOT_APPLICABLE
        )

    def test_game_day_registers_its_own_components(self):
        self.assertTrue({"schedule", "courts"} <= set(self.service.component_keys()))

    def test_a_failing_provider_is_blocked_never_ready(self):
        with patch.object(
            type(self.service), "_readiness_courts", side_effect=RuntimeError("boom")
        ):
            result = self.service.evaluate(self.matchday)
        courts = self._component(result, "courts")
        self.assertTrue(courts["error"])
        self.assertEqual(courts["status"], vocabulary.BLOCKED)
        self.assertEqual(result["overall"], vocabulary.BLOCKED)
        self.assertTrue(courts["blockers"][0]["action"])
        self.assertEqual(
            self._component(result, "schedule")["status"], vocabulary.ACTION_NEEDED
        )

    def test_counts_use_singular_and_plural_sentences(self):
        text = self.service._count_text(
            1, "%(count)s item needs work.", "%(count)s items need work."
        )
        self.assertEqual(text, "1 item needs work.")
        text = self.service._count_text(
            2, "%(count)s item needs work.", "%(count)s items need work."
        )
        self.assertEqual(text, "2 items need work.")

    def test_missing_owner_and_deadline_are_visible_not_invented(self):
        item = self.service._present(
            self.service._readiness_scope(self.matchday),
            vocabulary.project(
                [
                    vocabulary.make_component(
                        "courts",
                        vocabulary.ACTION_NEEDED,
                        "Action needed",
                        blockers=[
                            vocabulary.make_blocker(
                                key="courts-x",
                                status=vocabulary.ACTION_NEEDED,
                                problem="A problem.",
                                action="An action.",
                                destination=vocabulary.make_destination(
                                    "federation.matchday", res_id=self.matchday.id
                                ),
                            )
                        ],
                    )
                ]
            ),
        )["blockers"][0]
        self.assertIsNone(item["owner"])
        self.assertEqual(item["owner_label"], "No owner assigned")
        self.assertEqual(item["deadline_label"], "No deadline set")

    def test_backend_fields_follow_the_service(self):
        result = self.service.evaluate(self.matchday)
        self.assertEqual(self.matchday.readiness_overall, result["overall"])
        self.assertIn(result["headline"], str(self.matchday.readiness_summary))

    def test_new_unsaved_game_day_has_nothing_to_report(self):
        draft = self.env["federation.matchday"].new({"name": "Unsaved"})
        self.assertEqual(draft.readiness_overall, vocabulary.NOT_APPLICABLE)
        self.assertFalse(draft.readiness_summary)
