from odoo.tests import TransactionCase


class TestSanctionFinanceHooks(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.player = cls.env["federation.player"].create(
            {
                "name": "Sanctioned Player",
                "first_name": "Sanctioned",
                "last_name": "Player",
            }
        )
        cls.case = cls.env["federation.disciplinary.case"].create(
            {
                "name": "Finance Sanction Case",
                "subject_player_id": cls.player.id,
                "summary": "Finance bridge sanction coverage.",
            }
        )

    def test_fine_sanction_creates_finance_event(self):
        """Test that fine sanction creates finance event."""
        sanction = self.env["federation.sanction"].create(
            {
                "name": "Late payment fine",
                "case_id": self.case.id,
                "sanction_type": "fine",
                "amount": 125.0,
            }
        )

        event = self.env["federation.finance.event"].search(
            [
                ("source_model", "=", "federation.sanction"),
                ("source_res_id", "=", sanction.id),
            ],
            limit=1,
        )
        self.assertTrue(event)
        self.assertEqual(event.fee_type_id.code, "discipline_fine")
        self.assertEqual(event.player_id, self.player)
        self.assertEqual(event.amount, 125.0)
        self.assertEqual(event.event_type, "charge")
        self.assertTrue(event.external_ref)

    def test_warning_sanction_creates_no_finance_event(self):
        """Test that warning sanction creates no finance event."""
        sanction = self.env["federation.sanction"].create(
            {
                "name": "Written warning",
                "case_id": self.case.id,
                "sanction_type": "warning",
            }
        )

        count = self.env["federation.finance.event"].search_count(
            [
                ("source_model", "=", "federation.sanction"),
                ("source_res_id", "=", sanction.id),
            ]
        )
        self.assertEqual(count, 0)

    def test_fine_amount_updates_existing_draft_event(self):
        """Test that fine amount updates existing draft event."""
        sanction = self.env["federation.sanction"].create(
            {
                "name": "Appeal fine",
                "case_id": self.case.id,
                "sanction_type": "fine",
                "amount": 80.0,
            }
        )
        sanction.write({"amount": 95.0})

        event = self.env["federation.finance.event"].search(
            [
                ("source_model", "=", "federation.sanction"),
                ("source_res_id", "=", sanction.id),
            ],
            limit=1,
        )
        self.assertTrue(event)
        self.assertEqual(event.amount, 95.0)
