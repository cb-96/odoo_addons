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
        admin.write(
            {
                "group_ids": [
                    Command.link(
                        cls.env.ref(
                            "sports_federation_base.group_federation_manager"
                        ).id
                    ),
                    Command.link(
                        cls.env.ref(
                            "sports_federation_competition_core.group_competition_administrator"
                        ).id
                    ),
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
