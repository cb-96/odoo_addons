from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_setup_flow")
class TestCompetitionSetupConsolidation(TransactionCase):
    def test_legacy_workspace_action_uses_canonical_setup_router(self):
        Edition = self.env["federation.competition.edition"]
        self.assertEqual(
            Edition.action_open_next_workspace.__name__,
            "action_open_next_workspace",
        )
        self.assertTrue(hasattr(Edition, "action_continue_setup"))

    def test_readiness_service_has_one_operator_state_family(self):
        service = self.env["federation.competition.setup.readiness"]
        self.assertEqual(
            set(service.evaluate.__doc__.splitlines()[0:1]),
            {"Return the single operator-facing setup assessment."},
        )

    def test_advanced_workspace_remains_available(self):
        self.assertTrue(
            hasattr(
                self.env["federation.competition.edition"],
                "action_open_advanced_workspace",
            )
        )
