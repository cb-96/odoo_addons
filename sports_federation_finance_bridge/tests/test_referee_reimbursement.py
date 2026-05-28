from odoo.tests import TransactionCase


class TestRefereeReimbursementHooks(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Reimbursement Club",
                "code": "RFC",
            }
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "Reimbursement Team A",
                "club_id": cls.club.id,
                "code": "RTA",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "Reimbursement Team B",
                "club_id": cls.club.id,
                "code": "RTB",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Reimbursement Season",
                "code": "RFSEASON",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Reimbursement Tournament",
                "code": "RFT",
                "season_id": cls.season.id,
                "date_start": "2024-06-01",
            }
        )
        cls.match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.team_a.id,
                "away_team_id": cls.team_b.id,
                "state": "draft",
            }
        )
        cls.referee = cls.env["federation.referee"].create(
            {
                "name": "Reimbursement Referee",
                "certification_level": "national",
            }
        )
        cls.env["federation.fee.type"].create(
            {
                "name": "Referee Reimbursement",
                "code": "referee_reimbursement",
                "category": "reimbursement",
                "default_amount": 60.0,
            }
        )

    def test_done_assignment_creates_reimbursement_event(self):
        """Test that done assignment creates reimbursement event."""
        assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )

        assignment.action_confirm()
        assignment.action_done()

        event = self.env["federation.finance.event"].search(
            [
                ("source_model", "=", "federation.match.referee"),
                ("source_res_id", "=", assignment.id),
            ],
            limit=1,
        )
        self.assertTrue(event)
        self.assertEqual(event.fee_type_id.code, "referee_reimbursement")
        self.assertEqual(event.event_type, "reimbursement")
        self.assertEqual(event.referee_id, self.referee)
        self.assertEqual(event.amount, 60.0)

    def test_resetting_assignment_cancels_and_reuses_same_reimbursement_event(self):
        """Test that resetting assignment cancels and reuses same reimbursement event."""
        assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": self.referee.id,
                "role": "assistant_1",
            }
        )

        assignment.action_confirm()
        assignment.action_done()
        assignment.action_draft()

        event = self.env["federation.finance.event"].search(
            [
                ("source_model", "=", "federation.match.referee"),
                ("source_res_id", "=", assignment.id),
            ],
            limit=1,
        )
        self.assertTrue(event)
        self.assertEqual(event.state, "cancelled")

        assignment.action_confirm()
        assignment.action_done()

        self.assertEqual(
            self.env["federation.finance.event"].search_count(
                [
                    ("source_model", "=", "federation.match.referee"),
                    ("source_res_id", "=", assignment.id),
                ]
            ),
            1,
        )
        event.invalidate_recordset()
        self.assertEqual(event.state, "draft")
