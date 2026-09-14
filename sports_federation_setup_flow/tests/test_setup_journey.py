from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_setup_flow")
class TestCompetitionSetupJourney(TransactionCase):
    def test_creation_wizard_exposes_operator_defaults(self):
        fields = self.env["federation.create.competition.wizard"]._fields
        self.assertIn("workflow_mode", fields)
        self.assertIn("default_venue_id", fields)

    def test_gameday_setup_supports_recurring_days(self):
        fields = self.env["federation.competition.gameday.setup.wizard"]._fields
        self.assertIn("repeat_every_weeks", fields)
        self.assertIn("repeat_count", fields)

    def test_competition_can_open_clone_setup(self):
        self.assertTrue(
            hasattr(self.env["federation.competition.edition"], "action_open_clone_setup")
        )
