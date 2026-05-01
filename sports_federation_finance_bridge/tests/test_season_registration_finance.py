from odoo.tests import TransactionCase


class TestSeasonRegistrationFinance(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Finance Registration Club",
                "code": "FRC",
            }
        )
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Finance Registration Team",
                "club_id": cls.club.id,
                "code": "FRT",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Finance Registration Season",
                "code": "FRS2026",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )

    def test_confirm_creates_registration_finance_event(self):
        """Test that confirm creates registration finance event."""
        registration = self.env["federation.season.registration"].create(
            {
                "season_id": self.season.id,
                "team_id": self.team.id,
            }
        )

        registration.action_confirm()

        fee_type = self.env["federation.fee.type"].search(
            [("code", "=", "season_registration")],
            limit=1,
        )
        self.assertTrue(fee_type)
        event = self.env["federation.finance.event"].search(
            [
                ("fee_type_id", "=", fee_type.id),
                ("source_model", "=", "federation.season.registration"),
                ("source_res_id", "=", registration.id),
            ],
            limit=1,
        )
        self.assertTrue(event)
        self.assertEqual(event.club_id, self.club)
        self.assertEqual(event.state, "draft")
        self.assertEqual(event.event_type, "charge")

    def test_reconfirm_does_not_duplicate_registration_finance_event(self):
        """Test that reconfirm does not duplicate registration finance event."""
        registration = self.env["federation.season.registration"].create(
            {
                "season_id": self.season.id,
                "team_id": self.team.id,
            }
        )

        registration.action_confirm()
        registration.action_draft()
        registration.action_confirm()

        event_count = self.env["federation.finance.event"].search_count(
            [
                ("source_model", "=", "federation.season.registration"),
                ("source_res_id", "=", registration.id),
            ]
        )
        self.assertEqual(event_count, 1)

    def test_create_confirmed_registration_creates_finance_event(self):
        """Test that create confirmed registration creates finance event."""
        registration = self.env["federation.season.registration"].create(
            {
                "season_id": self.season.id,
                "team_id": self.team.id,
                "state": "confirmed",
            }
        )

        event_count = self.env["federation.finance.event"].search_count(
            [
                ("source_model", "=", "federation.season.registration"),
                ("source_res_id", "=", registration.id),
            ]
        )
        self.assertEqual(event_count, 1)
