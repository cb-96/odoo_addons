from odoo.tests.common import TransactionCase


class TestSeasonRegistrationHandoff(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {"name": "Roster Handoff Club", "code": "RHC1"}
        )
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Roster Handoff Team",
                "club_id": cls.club.id,
                "code": "RHT1",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Roster Handoff Season",
                "code": "RHS1",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.rule_set = cls.env["federation.rule.set"].create(
            {"name": "Roster Handoff Rules", "code": "RHR1"}
        )
        cls.competition = cls.env["federation.competition"].create(
            {
                "name": "Roster Handoff Competition",
                "code": "RHCMP",
                "rule_set_id": cls.rule_set.id,
            }
        )

    def test_action_open_team_rosters_prefills_roster_scope(self):
        """The season registration handoff should point operators at roster prep."""
        registration = self.env["federation.season.registration"].create(
            {
                "season_id": self.season.id,
                "team_id": self.team.id,
                "competition_id": self.competition.id,
                "rule_set_id": self.rule_set.id,
            }
        )

        action = registration.action_open_team_rosters()

        self.assertEqual(action["res_model"], "federation.team.roster")
        self.assertEqual(
            action["context"]["default_season_registration_id"], registration.id
        )
        self.assertEqual(action["context"]["default_team_id"], self.team.id)
        self.assertEqual(action["context"]["default_season_id"], self.season.id)
        self.assertEqual(
            action["context"]["default_competition_id"], self.competition.id
        )
        self.assertEqual(action["context"]["default_rule_set_id"], self.rule_set.id)
        self.assertEqual(
            action["domain"],
            [
                ("team_id", "=", self.team.id),
                ("season_id", "=", self.season.id),
                ("competition_id", "=", self.competition.id),
            ],
        )
