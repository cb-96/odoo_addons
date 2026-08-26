from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_portal_competition")
class TestPortalcurrentContract(TransactionCase):
    def test_competition_query_services_are_registered(self):
        self.assertIn("federation.portal.competition.queries", self.env)
        self.assertIn("federation.portal.matchday.queries", self.env)
        self.assertIn("federation.portal.scope", self.env)

    def test_competition_templates_are_loaded(self):
        for xmlid in (
            "sports_federation_portal.portal_my_competitions",
            "sports_federation_portal.portal_my_competition_detail",
            "sports_federation_portal.portal_my_matchdays",
            "sports_federation_portal.portal_my_matchday_detail",
            "sports_federation_portal.portal_matchday_operations_page",
        ):
            self.assertTrue(self.env.ref(xmlid))

    def test_legacy_workspace_templates_are_not_loaded(self):
        self.assertFalse(
            self.env.ref(
                "sports_federation_portal.portal_my_tournament_workspaces",
                raise_if_not_found=False,
            )
        )

    def test_portal_manifest_uses_competition_owners(self):
        module = self.env["ir.module.module"].search(
            [("name", "=", "sports_federation_portal")], limit=1
        )
        self.assertTrue(module)
        for dependency in (
            "sports_federation_competition_core",
            "sports_federation_registration",
            "sports_federation_schedule_approval",
            "sports_federation_matchday",
        ):
            self.assertIn(dependency, module.dependencies_id.mapped("name"))
