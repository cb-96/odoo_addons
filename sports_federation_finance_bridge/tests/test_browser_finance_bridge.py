from odoo.tests.common import HttpCase, tagged


@tagged("-at_install", "post_install", "sf_browser_finance_bridge")
class TestBrowserFinanceBridge(HttpCase):
    """Exercise the Finance Bridge lifecycle through the Odoo web client."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Browser Finance Season",
                "code": "BFS26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.club = cls.env["federation.club"].create(
            {"name": "Browser Finance Club", "code": "BFC26"}
        )
        cls.fee_type = cls.env["federation.fee.type"].create(
            {
                "name": "Browser Registration Fee",
                "code": "BROWSER_REG",
                "category": "registration",
                "default_amount": 125.0,
            }
        )
        cls.env["federation.fee.schedule"].create(
            {
                "season_id": cls.season.id,
                "fee_type_id": cls.fee_type.id,
                "category": "senior",
                "gender": "mixed",
                "amount": 125.0,
            }
        )
        cls.env["federation.season.budget"].create(
            {
                "season_id": cls.season.id,
                "fee_type_id": cls.fee_type.id,
                "budget_amount": 1000.0,
            }
        )
        cls.finance_event = cls.env["federation.finance.event"].create(
            {
                "name": "Browser Finance Lifecycle",
                "fee_type_id": cls.fee_type.id,
                "event_type": "charge",
                "amount": 125.0,
                "source_model": "federation.club",
                "source_res_id": cls.club.id,
                "season_id": cls.season.id,
                "club_id": cls.club.id,
                "external_ref": "BROWSER-FINANCE-LIFECYCLE",
            }
        )

    def test_finance_bridge_browser_lifecycle(self):
        self.start_tour(
            "/odoo/action-sports_federation_finance_bridge.action_federation_finance_event/"
            f"{self.finance_event.id}",
            "finance_bridge_browser_lifecycle",
            login="admin",
            timeout=180,
        )
        self.finance_event.invalidate_recordset()
        self.assertEqual(self.finance_event.state, "settled")
