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

    def test_gameday_court_relation_uses_postgresql_safe_name(self):
        field = self.env["federation.competition.gameday.setup.line"]._fields[
            "court_ids"
        ]
        self.assertEqual(
            field.relation,
            "federation_gameday_setup_line_playing_area_rel",
        )

    def test_participant_setup_action_is_scoped_to_edition(self):
        edition = self.env["federation.competition.edition"].browse(42)
        action = edition.action_setup_participants()
        self.assertEqual(action["domain"], [("edition_id", "=", 42)])
