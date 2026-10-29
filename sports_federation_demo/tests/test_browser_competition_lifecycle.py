from odoo import Command
from odoo.tests.common import HttpCase, tagged


@tagged(
    "-at_install",
    "post_install",
    "sf_browser_competition_lifecycle",
    "sf_release_confidence",
)
class TestBrowserCompetitionLifecycle(HttpCase):
    """Exercise every operator surface in the competition lifecycle.

    Domain transitions remain covered by the dedicated module Tours. This
    browser test protects integrated navigation, action loading, access
    groups, the test asset bundle, and the public competition handoff.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Use a normal internal account with explicit operator roles. Browser
        # lifecycle evidence must not depend on superuser access.
        lifecycle_group_xmlids = (
            "sports_federation_base.group_federation_manager",
            "sports_federation_competition_core.group_competition_administrator",
            "sports_federation_registration.group_registration_manager",
            "sports_federation_format.group_competition_designer",
            "sports_federation_calendar.group_calendar_planner",
            "sports_federation_scheduling.group_schedule_planner",
            "sports_federation_schedule_approval.group_schedule_approver",
            "sports_federation_matchday.group_matchday_manager",
        )
        groups = [
            cls.env.ref("base.group_user").id,
            *[cls.env.ref(xmlid).id for xmlid in lifecycle_group_xmlids],
        ]
        cls.lifecycle_operator = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Browser Lifecycle Operator",
                    "login": "browser.lifecycle.operator@example.invalid",
                    "email": "browser.lifecycle.operator@example.invalid",
                    "password": "admin",
                    "group_ids": [Command.set(groups)],
                }
            )
        )
        season = cls.env["federation.season"].create(
            {
                "name": "Browser Competition Lifecycle Season",
                "code": "BCLS26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        competition = cls.env["federation.competition"].create(
            {
                "name": "Browser Competition Lifecycle",
                "competition_type": "league",
            }
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Browser Competition Lifecycle",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )

    def test_full_competition_lifecycle_browser_tour(self):
        self.start_tour(
            "/odoo/action-sports_federation_setup_flow.action_competition_setup_home",
            "full_competition_lifecycle",
            login=self.lifecycle_operator.login,
            timeout=180,
        )

    def test_keyboard_competition_setup_browser_tour(self):
        self.start_tour(
            "/odoo/action-sports_federation_setup_flow.action_competition_setup_home",
            "keyboard_competition_setup",
            login=self.lifecycle_operator.login,
            timeout=180,
        )
