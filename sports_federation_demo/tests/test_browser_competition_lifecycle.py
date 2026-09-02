from odoo import Command
from odoo.tests.common import HttpCase, tagged


@tagged("-at_install", "post_install", "sf_browser_competition_lifecycle")
class TestBrowserCompetitionLifecycle(HttpCase):
    """Exercise every operator surface in the competition lifecycle.

    Domain transitions remain covered by the dedicated module Tours. This
    browser test protects integrated navigation, action loading, access
    groups, the test asset bundle, and the public competition handoff.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The overview form reads competition responsibilities and events, and
        # later tour steps open manager-only review and match-day menus. The
        # database's ``admin`` login is not automatically enrolled in custom
        # federation groups, so grant the explicit operator privileges that
        # this integrated lifecycle tour is intended to exercise.
        admin = cls.env.ref("base.user_admin")
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
        admin.write(
            {
                "group_ids": [
                    Command.link(cls.env.ref(xmlid).id)
                    for xmlid in lifecycle_group_xmlids
                ]
            }
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
            "/odoo/action-sports_federation_competition_core.action_competition_overview/"
            f"{self.edition.id}",
            "full_competition_lifecycle",
            login="admin",
            timeout=180,
        )

    def test_keyboard_competition_setup_browser_tour(self):
        self.start_tour(
            "/odoo/action-sports_federation_competition_core.action_competition_overview/"
            f"{self.edition.id}",
            "keyboard_competition_setup",
            login="admin",
            timeout=180,
        )
