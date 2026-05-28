import json

from odoo import SUPERUSER_ID, api
from odoo.addons.sports_federation_base.tests.route_inventory import (
    load_route_inventory,
)
from odoo.tests.common import HttpCase, tagged


@tagged("-at_install", "post_install")
class TestReportingHttpSmoke(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        with cls.registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            club = env["federation.club"].create(
                {
                    "name": "Reporting Smoke Club",
                    "code": "RSC",
                }
            )
            season = env["federation.season"].create(
                {
                    "name": "Reporting Smoke Season",
                    "code": "RSS",
                    "date_start": "2026-01-01",
                    "date_end": "2026-12-31",
                    "state": "open",
                }
            )
            tournament = env["federation.tournament"].create(
                {
                    "name": "Reporting Smoke Tournament",
                    "code": "RST",
                    "season_id": season.id,
                    "date_start": "2026-06-01",
                    "state": "open",
                }
            )
            team_a = env["federation.team"].create(
                {
                    "name": "Reporting Smoke Team A",
                    "club_id": club.id,
                    "code": "RSTA",
                    "category": "senior",
                    "gender": "male",
                }
            )
            team_b = env["federation.team"].create(
                {
                    "name": "Reporting Smoke Team B",
                    "club_id": club.id,
                    "code": "RSTB",
                    "category": "senior",
                    "gender": "male",
                }
            )
            participant_a = env["federation.tournament.participant"].create(
                {
                    "tournament_id": tournament.id,
                    "team_id": team_a.id,
                    "state": "confirmed",
                }
            )
            participant_b = env["federation.tournament.participant"].create(
                {
                    "tournament_id": tournament.id,
                    "team_id": team_b.id,
                    "state": "confirmed",
                }
            )
            rule_set = env["federation.rule.set"].create(
                {
                    "name": "Reporting Smoke Rules",
                    "code": "RSR",
                    "points_win": 3,
                    "points_draw": 1,
                    "points_loss": 0,
                }
            )
            standing = env["federation.standing"].create(
                {
                    "name": "Reporting Smoke Standing",
                    "tournament_id": tournament.id,
                    "rule_set_id": rule_set.id,
                }
            )
            env["federation.standing.line"].create(
                {
                    "standing_id": standing.id,
                    "participant_id": participant_a.id,
                    "rank": 1,
                    "played": 1,
                    "won": 1,
                    "drawn": 0,
                    "lost": 0,
                    "score_for": 2,
                    "score_against": 1,
                    "score_diff": 1,
                    "points": 3,
                }
            )
            env["federation.standing.line"].create(
                {
                    "standing_id": standing.id,
                    "participant_id": participant_b.id,
                    "rank": 2,
                    "played": 1,
                    "won": 0,
                    "drawn": 0,
                    "lost": 1,
                    "score_for": 1,
                    "score_against": 2,
                    "score_diff": -1,
                    "points": 0,
                }
            )
            fee_type = env["federation.fee.type"].create(
                {
                    "name": "Reporting Smoke Fee",
                    "code": "RSF",
                    "category": "registration",
                    "default_amount": 80.0,
                }
            )
            finance_event = env["federation.finance.event"].create(
                {
                    "name": "Reporting Smoke Finance Event",
                    "fee_type_id": fee_type.id,
                    "event_type": "charge",
                    "amount": 80.0,
                    "source_model": "federation.club",
                    "source_res_id": club.id,
                    "club_id": club.id,
                    "external_ref": "SMOKE-ROUTE-EXPORT",
                }
            )
            inbound_contract_code = env.ref(
                "sports_federation_import_tools.federation_integration_contract_clubs_csv"
            ).code
            cr.commit()

        cls.report_user = cls.env.ref("base.user_admin")
        cls.season = cls.env["federation.season"].browse(season.id)
        cls.tournament = cls.env["federation.tournament"].browse(tournament.id)
        cls.team_a = cls.env["federation.team"].browse(team_a.id)
        cls.fee_type = cls.env["federation.fee.type"].browse(fee_type.id)
        cls.finance_event = cls.env["federation.finance.event"].browse(finance_event.id)
        cls.inbound_contract = inbound_contract_code

    def _assert_csv_response(self, path, contract_name, expected_fragments):
        self.authenticate(self.report_user.login, "ignored")

        response = self.url_open(path)

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers.get("Content-Type", ""))
        self.assertEqual(response.headers.get("X-Federation-Contract"), contract_name)
        for fragment in expected_fragments:
            self.assertIn(fragment, response.text)
        self.assertNotIn("Internal Server Error", response.text)

    def _assert_json_401(self, path, data=None):
        response = self.url_open(path, data=data)

        self.assertEqual(response.status_code, 401)
        self.assertIn("application/json", response.headers.get("Content-Type", ""))
        payload = json.loads(response.text)
        self.assertEqual(payload["error_code"], "access_denied")
        self.assertNotIn("Internal Server Error", response.text)

    def test_standings_export_route_returns_csv(self):
        self._assert_csv_response(
            f"/reporting/export/standings/{self.tournament.id}",
            "standings_csv",
            [
                "Standing,Rank,Team,Club",
                "Reporting Smoke Standing",
                self.team_a.name,
            ],
        )

    def test_participation_export_route_returns_csv(self):
        self._assert_csv_response(
            f"/reporting/export/participation/{self.season.id}",
            "participation_csv",
            [
                "Tournament,Season,Team,Club,State",
                self.tournament.name,
                self.team_a.name,
            ],
        )

    def test_finance_export_route_returns_csv(self):
        self._assert_csv_response(
            "/reporting/export/finance",
            "finance_summary_csv",
            [
                "Fee Type,Category,State,Event Count,Total Amount",
                self.fee_type.name,
                "registration",
            ],
        )

    def test_finance_event_export_route_returns_csv(self):
        self._assert_csv_response(
            "/reporting/export/finance/events",
            self.env["federation.finance.event"].EXPORT_SCHEMA_VERSION,
            [
                "Schema Version,Event ID,Name,State,Handoff State,Event Type",
                self.finance_event.name,
                self.finance_event.external_ref,
            ],
        )

    def test_integration_contracts_route_returns_structured_401(self):
        self._assert_json_401("/integration/v1/contracts")

    def test_integration_finance_events_route_returns_structured_401(self):
        self._assert_json_401("/integration/v1/outbound/finance/events")

    def test_integration_inbound_delivery_route_returns_structured_401(self):
        self._assert_json_401(
            f"/integration/v1/inbound/{self.inbound_contract}/deliveries",
            data={"ignored": "1"},
        )

    def test_route_inventory_lists_smoke_covered_reporting_routes(self):
        inventory_routes = {
            (entry["method"], entry["path"])
            for entry in load_route_inventory("sports_federation_reporting")
        }

        self.assertEqual(
            inventory_routes,
            {
                ("GET", "/reporting/export/standings/<tournament_id>"),
                ("GET", "/reporting/export/participation/<season_id>"),
                ("GET", "/reporting/export/finance"),
                ("GET", "/reporting/export/finance/events"),
            },
        )

    def test_route_inventory_lists_smoke_covered_integration_routes(self):
        inventory_routes = {
            (entry["method"], entry["path"])
            for entry in load_route_inventory("sports_federation_import_tools")
        }

        self.assertEqual(
            inventory_routes,
            {
                ("GET", "/integration/v1/contracts"),
                ("GET", "/integration/v1/outbound/finance/events"),
                ("POST", "/integration/v1/inbound/<contract_code>/deliveries"),
            },
        )
