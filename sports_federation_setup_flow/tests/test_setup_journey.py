from datetime import date
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_setup_flow")
class TestCompetitionSetupJourney(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Setup source season",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        cls.next_season = cls.env["federation.season"].create(
            {
                "name": "Setup target season",
                "date_start": "2027-09-01",
                "date_end": "2028-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Setup test league", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Setup source edition",
                "competition_id": competition.id,
                "season_id": cls.season.id,
                "date_start": "2026-09-05",
                "date_end": "2027-06-05",
            }
        )
        cls.venue = cls.env["federation.venue"].create({"name": "Setup test venue"})
        cls.court = cls.env["federation.playing.area"].create(
            {"name": "Court 1", "venue_id": cls.venue.id}
        )

    def test_readiness_explains_next_blocker(self):
        result = self.env["federation.competition.setup.readiness"].evaluate(self.edition)
        self.assertEqual(result["step"], "basics")
        self.assertTrue(result["blocker_hint"])

    def test_continue_setup_opens_visual_planner(self):
        service = self.env["federation.competition.setup.readiness"]
        with patch.object(
            type(service),
            "evaluate",
            side_effect=AssertionError("legacy readiness routing must not be used"),
        ):
            action = self.edition.action_continue_setup()

        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(
            action["tag"], "sports_federation_setup_flow.CompetitionPlanner"
        )
        self.assertEqual(action["params"]["edition_id"], self.edition.id)

    def test_legacy_workspace_entry_point_opens_planner_for_edition(self):
        action = self.edition.action_open_next_workspace()

        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(
            action["tag"], "sports_federation_setup_flow.CompetitionPlanner"
        )
        self.assertEqual(action["params"]["edition_id"], self.edition.id)

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

    def test_clone_shortcut_opens_wizard_without_creating_incomplete_record(self):
        action = self.edition.action_open_clone_setup()
        self.assertEqual(
            action["res_model"], "federation.competition.clone.setup.wizard"
        )
        self.assertNotIn("res_id", action)
        self.assertEqual(
            action["context"]["default_source_edition_id"], self.edition.id
        )
        self.assertEqual(action["context"]["default_date_start"], date(2027, 9, 5))

    def test_clone_creates_draft_in_another_season(self):
        Wizard = self.env["federation.competition.clone.setup.wizard"]
        values = {
            "source_edition_id": self.edition.id,
            "name": "Setup copied edition",
            "season_id": self.next_season.id,
            "date_start": "2027-09-05",
            "date_end": "2028-06-05",
            "copy_gameday_pattern": False,
        }
        with self.assertRaises(ValidationError):
            Wizard.create({**values, "season_id": self.season.id}).action_copy_setup()
        action = Wizard.create(values).action_copy_setup()
        copied = self.env["federation.competition.edition"].browse(action["res_id"])
        self.assertEqual(copied.name, "Setup copied edition")
        self.assertEqual(copied.season_id, self.next_season)
        self.assertEqual(copied.state, "draft")

    def test_recurring_days_and_copy_last_day(self):
        wizard = self.env["federation.competition.gameday.setup.wizard"].create(
            {
                "edition_id": self.edition.id,
                "new_date": "2026-10-03",
                "default_venue_id": self.venue.id,
                "repeat_every_weeks": 2,
                "repeat_count": 2,
            }
        )
        wizard.action_add_recurring_days()
        self.assertEqual(
            wizard.line_ids.mapped("date"),
            [date(2026, 10, 3), date(2026, 10, 17)],
        )
        self.assertEqual(wizard.line_ids.mapped("venue_id"), self.venue)
        self.assertEqual(wizard.line_ids.mapped("court_ids"), self.court)
        wizard.action_copy_last_day()
        self.assertEqual(
            wizard.line_ids.mapped("date"),
            [date(2026, 10, 3), date(2026, 10, 17), date(2026, 10, 31)],
        )
