from pathlib import Path

from odoo.tests.common import TransactionCase, tagged


@tagged("-at_install", "post_install", "sf_release_focus")
class TestReleasePilotReadiness(TransactionCase):
    """Keep the deterministic release-pilot path wired end to end.

    Domain-level state transitions remain in their owning addons. This contract
    verifies that the integrated operator actions, public handoff, browser tours,
    and security groups needed by the release pilot are installed together.
    """

    ACTION_MODELS = {
        "sports_federation_competition_core.action_competition_overview": "federation.competition.edition",
        "sports_federation_registration.action_registration_desk": "federation.registration.window",
        "sports_federation_format.action_format_studio": "federation.competition.structure",
        "sports_federation_calendar.action_calendar_planner": "federation.matchday",
        "sports_federation_scheduling.action_schedule_planner_competition": "federation.schedule",
        "sports_federation_schedule_approval.action_schedule_review_queue": "federation.schedule.review",
        "sports_federation_matchday.action_matchday_control": "federation.matchday",
        "sports_federation_standings.action_federation_standing": "federation.standing",
    }

    REQUIRED_GROUPS = (
        "sports_federation_base.group_federation_manager",
        "sports_federation_competition_core.group_competition_administrator",
        "sports_federation_registration.group_registration_manager",
        "sports_federation_format.group_competition_designer",
        "sports_federation_calendar.group_calendar_planner",
        "sports_federation_scheduling.group_schedule_planner",
        "sports_federation_schedule_approval.group_schedule_approver",
        "sports_federation_matchday.group_matchday_manager",
        "sports_federation_portal.group_federation_portal_club",
    )

    REQUIRED_TOURS = (
        "sports_federation_demo/static/tests/tours/full_competition_lifecycle_tour.js",
        "sports_federation_finance_bridge/static/tests/tours/finance_bridge_browser_tour.js",
        "sports_federation_public_site/static/tests/tours/public_site_browser_tour.js",
    )

    def test_release_pilot_actions_target_the_canonical_models(self):
        for xmlid, expected_model in self.ACTION_MODELS.items():
            action = self.env.ref(xmlid)
            self.assertEqual(action.res_model, expected_model, xmlid)

    def test_release_pilot_security_roles_are_installed(self):
        for xmlid in self.REQUIRED_GROUPS:
            self.assertTrue(self.env.ref(xmlid), xmlid)

    def test_release_pilot_browser_assets_are_present(self):
        repository_root = Path(__file__).resolve().parents[2]
        for relative_path in self.REQUIRED_TOURS:
            path = repository_root / relative_path
            self.assertTrue(path.is_file(), relative_path)
            source = path.read_text(encoding="utf-8")
            self.assertIn('registry.category("web_tour.tours")', source)
            forbidden_architecture_tokens = (
                "competitions_current",
                "competition_current",
            )
            normalized_source = source.lower()
            for token in forbidden_architecture_tokens:
                self.assertNotIn(token, normalized_source)

    def test_keyboard_setup_tour_uses_keyboard_activation_and_focus_assertions(self):
        path = (
            Path(__file__).resolve().parents[1]
            / "static/tests/tours/keyboard_competition_setup_tour.js"
        )
        source = path.read_text(encoding="utf-8")
        self.assertIn('key: "Enter"', source)
        self.assertIn("document.activeElement", source)
        for xmlid in (
            "sports_federation_competition_core.action_competition_overview",
            "sports_federation_registration.action_registration_desk",
            "sports_federation_format.action_format_studio",
            "sports_federation_calendar.action_calendar_planner",
            "sports_federation_scheduling.action_schedule_planner_competition",
            "sports_federation_schedule_approval.action_schedule_review_queue",
        ):
            self.assertIn(xmlid, source)
