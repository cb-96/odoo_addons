from odoo.tests.common import TransactionCase


class TestCompetitionPlanner(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Planner Season",
                "code": "PLAN-2027",
                "date_start": "2027-01-01",
                "date_end": "2027-12-31",
            }
        )
        cls.competition = cls.env["federation.competition"].create(
            {
                "name": "Planner Competition",
                "code": "PLAN",
                "competition_type": "league",
            }
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Planner Competition 2027",
                "competition_id": cls.competition.id,
                "season_id": cls.season.id,
                "date_start": "2027-02-01",
                "date_end": "2027-10-31",
            }
        )

    def test_continue_setup_opens_visual_planner(self):
        action = self.edition.action_continue_setup()

        self.assertEqual(action["type"], "ir.actions.client")
        self.assertEqual(
            action["tag"], "sports_federation_setup_flow.CompetitionPlanner"
        )
        self.assertEqual(action["params"]["edition_id"], self.edition.id)

    def test_planner_exposes_ordered_journey_and_first_blocker(self):
        data = self.edition.get_competition_planner_data()

        self.assertEqual(
            [step["key"] for step in data["steps"]],
            ["basics", "teams", "format", "gamedays", "schedule", "publication"],
        )
        self.assertEqual(data["current_step"], "basics")
        self.assertFalse(data["complete"])
        self.assertEqual(data["counts"]["divisions"], 0)
        self.assertIn("missing-divisions", [issue["key"] for issue in data["issues"]])

    def test_step_actions_keep_competition_scope(self):
        action = self.edition.action_open_planner_step("gamedays")

        self.assertEqual(action["res_model"], "federation.matchday")
        self.assertEqual(action["domain"], [("edition_id", "=", self.edition.id)])
        self.assertEqual(action["context"]["default_edition_id"], self.edition.id)
        self.assertEqual(action["view_mode"], "calendar,list,form")
