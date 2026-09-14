from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_setup_flow")
class TestCompetitionSetupFlow(TransactionCase):
    def test_new_edition_starts_with_divisions(self):
        edition = self.env["federation.competition.edition"].new({})
        self.assertIn("setup_step", edition._fields)

    def test_gameday_wizard_keeps_edition_context(self):
        self.assertIn(
            "edition_id",
            self.env["federation.competition.gameday.setup.wizard"]._fields,
        )
