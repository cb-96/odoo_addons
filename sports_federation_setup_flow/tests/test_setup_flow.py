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
        season = self.env["federation.season"].create(
            {
                "name": "Participant Setup Season",
                "code": "PART-SETUP",
                "date_start": "2027-01-01",
                "date_end": "2027-12-31",
            }
        )
        competition = self.env["federation.competition"].create(
            {
                "name": "Participant Setup Competition",
                "code": "PART-SETUP",
                "competition_type": "league",
            }
        )
        edition = self.env["federation.competition.edition"].create(
            {
                "name": "Participant Setup Edition",
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2027-02-01",
                "date_end": "2027-10-31",
            }
        )
        division = self.env["federation.tournament"].create(
            {
                "name": "Participant Setup Division",
                "edition_id": edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2027-02-01",
            }
        )

        action = edition.action_setup_participants()

        self.assertEqual(
            action["res_model"], "federation.competition.team.selection.wizard"
        )
        wizard = self.env[action["res_model"]].browse(action["res_id"])
        self.assertEqual(wizard.edition_id, edition)
        self.assertEqual(wizard.division_id, division)
