"""Release gate for the authoritative game-day readiness.

The planner, the backend match-day screen and the live workspace must all show
the answer of one service. These tests run that service against a persisted,
published game day with every readiness provider installed.
"""

from odoo.addons.sports_federation_base import readiness_vocabulary as vocabulary
from odoo.addons.sports_federation_duty_coverage.tests.common import CoverageFixture
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "sf_release_confidence", "sf_matchday_readiness")
class TestMatchdayReadinessRelease(CoverageFixture, TransactionCase):
    def setUp(self):
        super().setUp()
        self.service = self.env["federation.matchday.readiness"]
        self.matchday = self.match.schedule_publication_id.matchday_id

    def test_every_component_has_exactly_one_registered_provider(self):
        keys = self.service.component_keys()
        self.assertCountEqual(keys, vocabulary.COMPONENT_ORDER)
        self.assertEqual(len(keys), len(set(keys)))

    def test_projection_covers_every_component_without_provider_errors(self):
        result = self.service.evaluate(self.matchday)
        self.assertEqual(
            [component["key"] for component in result["components"]],
            list(vocabulary.COMPONENT_ORDER),
        )
        for component in result["components"]:
            self.assertFalse(component["error"], component)
            self.assertIn(component["status"], vocabulary.STATUSES)
            if component["status"] in vocabulary.ATTENTION:
                self.assertTrue(component["blockers"], component)

    def test_every_blocker_names_problem_owner_deadline_action_destination(self):
        result = self.service.evaluate(self.matchday)
        self.assertTrue(result["blockers"])
        for blocker in result["blockers"]:
            for field in ("problem", "owner", "deadline", "action", "destination"):
                self.assertIn(field, blocker)
            self.assertTrue(blocker["problem"])
            self.assertTrue(blocker["action"])
            self.assertTrue(blocker["destination"]["model"])
            self.assertTrue(blocker["owner_label"])
            self.assertTrue(blocker["deadline_label"])

    def test_unprepared_game_day_cannot_run(self):
        result = self.service.evaluate(self.matchday)
        self.assertFalse(result["can_run"])
        self.assertNotEqual(result["overall"], vocabulary.READY)
        by_key = {component["key"]: component for component in result["components"]}
        self.assertEqual(by_key["schedule"]["status"], vocabulary.READY)
        self.assertNotEqual(by_key["rosters"]["status"], vocabulary.READY)

    def test_backend_screen_shows_the_service_answer(self):
        result = self.service.evaluate(self.matchday)
        self.assertEqual(self.matchday.readiness_overall, result["overall"])
        self.assertIn(result["headline"], str(self.matchday.readiness_summary))

    def test_operator_view_hides_owners_and_destinations(self):
        brief = self.service.brief(self.matchday)
        for component in brief["components"]:
            self.assertNotIn("blockers", component)
        for blocker in brief["blockers"]:
            self.assertNotIn("owner", blocker)
            self.assertNotIn("destination", blocker)
            self.assertTrue(blocker["action"])

    def test_officials_use_the_acceptance_aware_provider(self):
        component = next(
            item
            for item in self.service.evaluate(self.matchday)["components"]
            if item["key"] == "officials"
        )
        self.assertFalse(component["error"])
        if not self.match.coverage_owner_id:
            for blocker in component["blockers"]:
                self.assertIsNone(blocker["owner"])
                self.assertEqual(blocker["owner_state"], vocabulary.OWNER_UNASSIGNED)
