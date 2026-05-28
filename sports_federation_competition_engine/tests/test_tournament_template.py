from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase


class TestCompetitionEngineWizardGuards(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {"name": "Wizard Club", "code": "WCLUB"}
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Wizard Season",
                "code": "WSEASON",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Wizard Tournament",
                "code": "WTOUR",
                "season_id": cls.season.id,
                "date_start": "2026-02-01",
                "state": "open",
            }
        )
        cls.stage = cls.env["federation.tournament.stage"].create(
            {
                "name": "Wizard Stage",
                "tournament_id": cls.tournament.id,
                "stage_type": "group",
            }
        )
        cls.knockout_stage = cls.env["federation.tournament.stage"].create(
            {
                "name": "Wizard Knockout",
                "tournament_id": cls.tournament.id,
                "stage_type": "knockout",
                "sequence": 20,
            }
        )
        cls.participants = cls.env["federation.tournament.participant"]
        for index in range(1, 5):
            team = cls.env["federation.team"].create(
                {
                    "name": f"Wizard Team {index}",
                    "club_id": cls.club.id,
                    "code": f"WT{index}",
                }
            )
            cls.participants |= cls.env["federation.tournament.participant"].create(
                {
                    "tournament_id": cls.tournament.id,
                    "stage_id": cls.stage.id,
                    "team_id": team.id,
                    "state": "confirmed",
                    "seed": index,
                }
            )
        # Pre-create gamedays so the wizard summary can compute properly
        for i in range(1, 4):
            cls.env["federation.tournament.round"].create(
                {
                    "stage_id": cls.stage.id,
                    "sequence": i,
                    "name": f"Gameday {i}",
                }
            )

    def test_round_robin_wizard_requires_rule_set(self):
        """Test that round robin wizard requires rule set."""
        wizard = self.env["federation.round.robin.wizard"].create(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.stage.id,
            }
        )

        with self.assertRaises(UserError):
            wizard.action_generate()

    def test_round_robin_wizard_computes_preview_summary(self):
        """Test that round robin wizard computes preview summary."""
        wizard = self.env["federation.round.robin.wizard"].new(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.stage.id,
                "use_all_participants": True,
                "round_type": "single",
                "rounds_count": 1,
            }
        )

        wizard._compute_summary()

        self.assertIn("4 participants", wizard.summary)
        self.assertIn("6 total matches", wizard.summary)

    def test_round_robin_wizard_summary_explains_confirmed_scope_requirement(self):
        """Test that round robin wizard summary explains confirmed scope requirement."""
        self.participants[:3].write({"state": "registered"})
        wizard = self.env["federation.round.robin.wizard"].new(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.stage.id,
                "use_all_participants": True,
            }
        )

        wizard._compute_summary()

        self.assertIn("confirmed participants", wizard.summary)
        self.assertIn("Found 1 confirmed", wizard.summary)

    def test_round_robin_wizard_rejects_selected_unconfirmed_participants(self):
        """Test that round robin wizard rejects selected unconfirmed participants."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Wizard Rule Set",
                "code": "WRS",
            }
        )
        self.tournament.rule_set_id = rule_set.id
        self.participants[0].state = "registered"
        wizard = self.env["federation.round.robin.wizard"].create(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.stage.id,
                "use_all_participants": False,
                "participant_ids": [(6, 0, self.participants[:2].ids)],
            }
        )

        with self.assertRaises(UserError):
            wizard.action_generate()

    def test_knockout_wizard_requires_rule_set(self):
        """Test that knockout wizard requires rule set."""
        wizard = self.env["federation.knockout.wizard"].create(
            {
                "tournament_id": self.tournament.id,
                "stage_id": self.knockout_stage.id,
                "participant_source": "tournament",
            }
        )

        with self.assertRaises(UserError):
            wizard.action_generate()


class TestTournamentTemplate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Template Season",
                "code": "TSEASON",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Template Tournament",
                "code": "TTOUR",
                "season_id": cls.season.id,
                "date_start": "2026-03-01",
            }
        )

    def test_template_apply_creates_stages_groups_and_progressions(self):
        """Test that template apply creates stages groups and progressions."""
        template = self.env["federation.tournament.template"].create(
            {
                "name": "Two Stage Template",
            }
        )
        group_line = self.env["federation.tournament.template.line"].create(
            {
                "template_id": template.id,
                "sequence": 10,
                "stage_name": "Group Phase",
                "stage_type": "group",
                "format": "round_robin",
                "group_count": 2,
                "teams_per_group": 4,
            }
        )
        knockout_line = self.env["federation.tournament.template.line"].create(
            {
                "template_id": template.id,
                "sequence": 20,
                "stage_name": "Final Stage",
                "stage_type": "knockout",
                "format": "knockout",
                "group_count": 1,
            }
        )
        self.env["federation.tournament.template.progression"].create(
            {
                "template_id": template.id,
                "sequence": 10,
                "source_line_id": group_line.id,
                "target_line_id": knockout_line.id,
                "rank_from": 1,
                "rank_to": 2,
                "seeding_method": "keep_rank",
                "auto_advance": True,
            }
        )

        stage_map = template.action_apply(self.tournament)

        self.assertEqual(len(stage_map), 2)
        group_stage = self.tournament.stage_ids.filtered(
            lambda stage: stage.name == "Group Phase"
        )
        knockout_stage = self.tournament.stage_ids.filtered(
            lambda stage: stage.name == "Final Stage"
        )
        self.assertEqual(len(group_stage.group_ids), 2)

        progression = self.env["federation.stage.progression"].search(
            [
                ("tournament_id", "=", self.tournament.id),
                ("source_stage_id", "=", group_stage.id),
                ("target_stage_id", "=", knockout_stage.id),
            ],
            limit=1,
        )
        self.assertTrue(progression)
        self.assertTrue(progression.auto_advance)

    def test_template_apply_rejects_tournament_with_existing_stages(self):
        """Test that template apply rejects tournament with existing stages."""
        template = self.env["federation.tournament.template"].create(
            {"name": "Existing Stage Template"}
        )
        self.env["federation.tournament.template.line"].create(
            {
                "template_id": template.id,
                "sequence": 10,
                "stage_name": "Only Stage",
                "stage_type": "group",
                "format": "round_robin",
                "group_count": 1,
            }
        )
        self.env["federation.tournament.stage"].create(
            {
                "name": "Existing Stage",
                "tournament_id": self.tournament.id,
                "stage_type": "group",
            }
        )

        with self.assertRaises(UserError):
            template.action_apply(self.tournament)
