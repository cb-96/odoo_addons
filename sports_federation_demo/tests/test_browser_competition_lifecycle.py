from odoo.tests.common import HttpCase, tagged


@tagged("-at_install", "post_install", "sf_browser_competition_lifecycle")
class TestBrowserCompetitionLifecycle(HttpCase):
    """Exercise every operator surface in the competition lifecycle.

    Domain transitions remain covered by the dedicated module Tours. This
    browser test protects integrated navigation, action loading, access
    groups, the test asset bundle, and the public competition handoff.
    """

    def test_full_competition_lifecycle_browser_tour(self):
        self.start_tour(
            "/odoo/action-sports_federation_competition_core.action_competition_overview/",
            "full_competition_lifecycle",
            login="admin",
            timeout=180,
        )
