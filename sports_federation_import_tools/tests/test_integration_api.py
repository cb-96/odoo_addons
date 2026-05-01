import csv
from datetime import datetime
import io
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from odoo.addons.sports_federation_base.exceptions import (
    AttachmentScanVerificationError,
)
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase

from odoo.addons.sports_federation_import_tools.controllers.integration_api_auth_mixin import (
    FederationIntegrationApiAuthMixin,
)
from odoo.addons.sports_federation_import_tools.controllers.integration_api import (
    FederationIntegrationApi,
)
from odoo.addons.sports_federation_import_tools.controllers.integration_api_response_mixin import (
    FederationIntegrationApiResponseMixin,
)


class TestIntegrationApi(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.controller = FederationIntegrationApi()
        cls.contract = cls.env.ref(
            "sports_federation_import_tools.federation_integration_contract_finance_event"
        )
        cls.inbound_contract = cls.env.ref(
            "sports_federation_import_tools.federation_integration_contract_clubs_csv"
        )
        cls.partner = cls.env["federation.integration.partner"].create(
            {
                "name": "API Partner",
                "code": "API_PARTNER",
            }
        )
        cls.env["federation.integration.partner.contract"].create(
            {
                "partner_id": cls.partner.id,
                "contract_id": cls.contract.id,
            }
        )
        cls.env["federation.integration.partner.contract"].create(
            {
                "partner_id": cls.partner.id,
                "contract_id": cls.inbound_contract.id,
            }
        )
        cls.raw_token = cls.partner._issue_auth_token()

    def _make_request(
        self, headers=None, params=None, json_payload=None, remote_addr="198.51.100.20"
    ):
        return SimpleNamespace(
            httprequest=SimpleNamespace(
                headers=headers or {},
                remote_addr=remote_addr,
                get_json=lambda silent=True: json_payload,
            ),
            params=params or {},
            env=self.env,
        )

    def _make_finance_request(self, finance_event_service, params=None):
        return SimpleNamespace(
            httprequest=SimpleNamespace(
                headers={
                    "X-Federation-Partner-Code": self.partner.code,
                    "X-Federation-Partner-Token": self.raw_token,
                },
                remote_addr="198.51.100.20",
                get_json=lambda silent=True: {},
            ),
            params=params or {},
            env=SimpleNamespace(
                get=lambda model_name: (
                    finance_event_service
                    if model_name == "federation.finance.event"
                    else None
                )
            ),
        )

    def test_integration_api_controller_composes_split_helpers(self):
        self.assertIsInstance(self.controller, FederationIntegrationApiAuthMixin)
        self.assertIsInstance(self.controller, FederationIntegrationApiResponseMixin)
        self.assertTrue(hasattr(self.controller, "_get_credentials"))
        self.assertTrue(hasattr(self.controller, "_json_error_response"))

    def test_get_credentials_accepts_custom_headers(self):
        request_stub = self._make_request(
            headers={
                "X-Federation-Partner-Code": self.partner.code,
                "X-Federation-Partner-Token": self.raw_token,
            }
        )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ):
            partner_code, token = self.controller._get_credentials()

        self.assertEqual(partner_code, self.partner.code)
        self.assertEqual(token, self.raw_token)

    def test_get_credentials_accepts_bearer_authorization(self):
        request_stub = self._make_request(
            headers={
                "X-Federation-Partner-Code": self.partner.code,
                "Authorization": f"Bearer {self.raw_token}",
            }
        )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ):
            partner_code, token = self.controller._get_credentials()

        self.assertEqual(partner_code, self.partner.code)
        self.assertEqual(token, self.raw_token)

    def test_get_credentials_rejects_query_string_credentials(self):
        request_stub = self._make_request(
            params={
                "partner_code": self.partner.code,
                "access_token": self.raw_token,
            }
        )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ), self.assertRaises(AccessError):
            self.controller._get_credentials()

    def test_get_credentials_rejects_mixed_header_and_query_credentials(self):
        request_stub = self._make_request(
            headers={
                "X-Federation-Partner-Code": self.partner.code,
                "X-Federation-Partner-Token": self.raw_token,
            },
            params={
                "access_token": "leaked-token",
            },
        )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ), self.assertRaises(AccessError):
            self.controller._get_credentials()

    def test_contracts_route_returns_401_for_query_string_credentials(self):
        request_stub = self._make_request(
            params={
                "partner_code": self.partner.code,
                "access_token": self.raw_token,
            }
        )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ):
            response = self.controller.integration_contracts()

        self.assertEqual(response.status_code, 401)
        payload = json.loads(response.get_data(as_text=True))
        self.assertEqual(payload["error_code"], "access_denied")
        self.assertIn("headers only", payload["error"])

    def test_inbound_route_returns_400_for_disallowed_payload_extension(self):
        request_stub = self._make_request(
            headers={
                "X-Federation-Partner-Code": self.partner.code,
                "X-Federation-Partner-Token": self.raw_token,
            },
            json_payload={
                "filename": "clubs.json",
                "payload_base64": "bmFtZTtjb2RlClN0YWdlZCBDbHViO1NDMDAx",
            },
        )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ):
            response = self.controller.integration_stage_inbound_delivery(
                self.inbound_contract.code
            )

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.get_data(as_text=True))
        self.assertEqual(payload["error_code"], "data_validation")
        self.assertIn("extensions", payload["error"])

    def test_inbound_route_returns_503_when_scanner_cannot_verify_payload(self):
        request_stub = self._make_request(
            headers={
                "X-Federation-Partner-Code": self.partner.code,
                "X-Federation-Partner-Token": self.raw_token,
            },
            json_payload={
                "filename": "clubs.csv",
                "payload_base64": "bmFtZTtjb2RlClN0YWdlZCBDbHViO1NDMDAx",
                "content_type": "text/csv",
            },
        )
        scanner = self.env["federation.attachment.scan.service"]

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ), patch.object(
            type(scanner),
            "scan_upload",
            side_effect=AttachmentScanVerificationError(
                "Uploaded files could not be verified by the federation malware scanner. Try again later."
            ),
        ):
            response = self.controller.integration_stage_inbound_delivery(
                self.inbound_contract.code
            )

        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.get_data(as_text=True))
        self.assertEqual(payload["error_code"], "retryable_delivery")
        self.assertIn("Try again later", payload["error"])

    def test_inbound_route_accepts_idempotency_key_header(self):
        request_stub = self._make_request(
            headers={
                "X-Federation-Partner-Code": self.partner.code,
                "X-Federation-Partner-Token": self.raw_token,
                "X-Federation-Idempotency-Key": "delivery-001",
            },
            json_payload={
                "filename": "clubs.csv",
                "payload_base64": "bmFtZTtjb2RlCklkZW1wb3RlbnQgQ2x1YjtJREMwMDE=",
                "content_type": "text/csv",
                "source_reference": "batch-300",
            },
        )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ):
            response = self.controller.integration_stage_inbound_delivery(
                self.inbound_contract.code
            )

        self.assertEqual(response.status_code, 201)
        payload = json.loads(response.get_data(as_text=True))
        self.assertEqual(
            response.headers.get("X-Federation-Delivery-Outcome"), "created"
        )
        self.assertEqual(
            response.headers.get("X-Federation-Idempotency-Key"), "delivery-001"
        )
        self.assertEqual(
            response.headers.get("X-Federation-Idempotent-Replay"), "false"
        )
        self.assertEqual(payload["delivery_outcome"], "created")
        self.assertEqual(payload["delivery"]["idempotency_key"], "delivery-001")
        delivery = self.env["federation.integration.delivery"].browse(
            payload["delivery"]["id"]
        )
        self.assertEqual(delivery.idempotency_key, "delivery-001")

    def test_inbound_route_returns_400_for_conflicting_idempotency_key(self):
        first_request = self._make_request(
            headers={
                "X-Federation-Partner-Code": self.partner.code,
                "X-Federation-Partner-Token": self.raw_token,
                "X-Federation-Idempotency-Key": "delivery-002",
            },
            json_payload={
                "filename": "clubs.csv",
                "payload_base64": "bmFtZTtjb2RlCklkZW1wb3RlbnQgQ2x1YjtJREMwMDE=",
                "content_type": "text/csv",
                "source_reference": "batch-400",
            },
        )
        second_request = self._make_request(
            headers={
                "X-Federation-Partner-Code": self.partner.code,
                "X-Federation-Partner-Token": self.raw_token,
                "X-Federation-Idempotency-Key": "delivery-002",
            },
            json_payload={
                "filename": "clubs.csv",
                "payload_base64": "bmFtZTtjb2RlCkRpZmZlcmVudCBDbHViO0lEQzAwMg==",
                "content_type": "text/csv",
                "source_reference": "batch-401",
            },
        )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            first_request,
        ):
            first_response = self.controller.integration_stage_inbound_delivery(
                self.inbound_contract.code
            )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            second_request,
        ):
            second_response = self.controller.integration_stage_inbound_delivery(
                self.inbound_contract.code
            )

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 400)
        payload = json.loads(second_response.get_data(as_text=True))
        self.assertEqual(payload["error_code"], "data_validation")
        self.assertIn("idempotency key", payload["error"].lower())

    def test_inbound_route_marks_idempotent_replay_in_headers(self):
        request_stub = self._make_request(
            headers={
                "X-Federation-Partner-Code": self.partner.code,
                "X-Federation-Partner-Token": self.raw_token,
                "X-Federation-Idempotency-Key": "delivery-003",
            },
            json_payload={
                "filename": "clubs.csv",
                "payload_base64": "bmFtZTtjb2RlCklkZW1wb3RlbnQgQ2x1YjtJREMwMDE=",
                "content_type": "text/csv",
                "source_reference": "batch-402",
            },
        )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ):
            first_response = self.controller.integration_stage_inbound_delivery(
                self.inbound_contract.code
            )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ):
            second_response = self.controller.integration_stage_inbound_delivery(
                self.inbound_contract.code
            )

        first_payload = json.loads(first_response.get_data(as_text=True))
        second_payload = json.loads(second_response.get_data(as_text=True))
        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)
        self.assertEqual(
            first_response.headers.get("X-Federation-Delivery-Outcome"), "created"
        )
        self.assertEqual(
            second_response.headers.get("X-Federation-Delivery-Outcome"),
            "idempotency_replay",
        )
        self.assertEqual(
            first_response.headers.get("X-Federation-Idempotent-Replay"), "false"
        )
        self.assertEqual(
            second_response.headers.get("X-Federation-Idempotent-Replay"), "true"
        )
        self.assertEqual(first_payload["delivery_outcome"], "created")
        self.assertEqual(second_payload["delivery_outcome"], "idempotency_replay")
        self.assertEqual(
            first_payload["delivery"]["id"], second_payload["delivery"]["id"]
        )

    def test_inbound_route_exposes_checksum_reuse_without_idempotency_key(self):
        request_stub = self._make_request(
            headers={
                "X-Federation-Partner-Code": self.partner.code,
                "X-Federation-Partner-Token": self.raw_token,
            },
            json_payload={
                "filename": "clubs.csv",
                "payload_base64": "bmFtZTtjb2RlCkR1cGxpY2F0ZSBDbHViO0RVUDAwMQ==",
                "content_type": "text/csv",
                "source_reference": "batch-403",
            },
        )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ):
            first_response = self.controller.integration_stage_inbound_delivery(
                self.inbound_contract.code
            )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ):
            second_response = self.controller.integration_stage_inbound_delivery(
                self.inbound_contract.code
            )

        first_payload = json.loads(first_response.get_data(as_text=True))
        second_payload = json.loads(second_response.get_data(as_text=True))
        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)
        self.assertEqual(
            first_response.headers.get("X-Federation-Delivery-Outcome"), "created"
        )
        self.assertEqual(
            second_response.headers.get("X-Federation-Delivery-Outcome"),
            "checksum_reuse",
        )
        self.assertIsNone(second_response.headers.get("X-Federation-Idempotent-Replay"))
        self.assertEqual(first_payload["delivery_outcome"], "created")
        self.assertEqual(second_payload["delivery_outcome"], "checksum_reuse")
        self.assertEqual(
            first_payload["delivery"]["id"], second_payload["delivery"]["id"]
        )

    def test_contracts_route_rate_limits_repeat_callers(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.rate_limit.integration_contracts.limit",
            1,
        )
        request_stub = self._make_request(
            headers={
                "X-Federation-Partner-Code": self.partner.code,
                "X-Federation-Partner-Token": self.raw_token,
            }
        )
        rate_limit_service = self.env["federation.request.rate.limit"].sudo()
        frozen_time = datetime(2026, 4, 18, 12, 0, 0)

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ), patch.object(
            type(rate_limit_service),
            "_get_now",
            return_value=frozen_time,
        ):
            response = self.controller.integration_contracts()
            blocked = self.controller.integration_contracts()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.headers.get("Retry-After"), "60")
        payload = json.loads(blocked.get_data(as_text=True))
        self.assertEqual(payload["error_code"], "retryable_delivery")

    def test_finance_events_route_rate_limits_repeat_callers(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.rate_limit.integration_finance_events.limit",
            1,
        )
        request_stub = self._make_request(
            headers={
                "X-Federation-Partner-Code": self.partner.code,
                "X-Federation-Partner-Token": self.raw_token,
            }
        )
        rate_limit_service = self.env["federation.request.rate.limit"].sudo()
        frozen_time = datetime(2026, 4, 18, 12, 0, 0)

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ), patch.object(
            type(rate_limit_service),
            "_get_now",
            return_value=frozen_time,
        ):
            response = self.controller.integration_finance_events()
            blocked = self.controller.integration_finance_events()

        self.assertNotEqual(response.status_code, 429)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.headers.get("Retry-After"), "60")
        payload = json.loads(blocked.get_data(as_text=True))
        self.assertEqual(payload["error_code"], "retryable_delivery")

    def test_finance_events_route_supports_cursor_pagination(self):
        newest = Mock()
        newest.get_handoff_export_row.return_value = [
            "finance_event_v1",
            "301",
            "Newest API Export Event",
        ]
        middle = Mock()
        middle.get_handoff_export_row.return_value = [
            "finance_event_v1",
            "300",
            "Middle API Export Event",
        ]
        oldest = Mock()
        oldest.get_handoff_export_row.return_value = [
            "finance_event_v1",
            "299",
            "Oldest API Export Event",
        ]
        finance_service = Mock()
        finance_service.EXPORT_SCHEMA_VERSION = "finance_event_v1"
        finance_service.sudo.return_value = finance_service
        finance_service.get_handoff_export_headers.return_value = [
            "Version",
            "Id",
            "Name",
        ]
        finance_service.get_handoff_export_batch.side_effect = [
            {
                "events": [newest, middle],
                "count": 2,
                "limit": 2,
                "has_more": True,
                "next_cursor": "2026-04-18 12:00:00|300",
            },
            {
                "events": [oldest],
                "count": 1,
                "limit": 2,
                "has_more": False,
                "next_cursor": False,
            },
        ]

        first_request = self._make_finance_request(
            finance_service,
            params={"limit": "2"},
        )
        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            first_request,
        ), patch.object(
            self.controller,
            "_rate_limit_response",
            return_value=False,
        ), patch.object(
            self.controller,
            "_authenticate",
            return_value=(SimpleNamespace(code=self.partner.code), None),
        ):
            first_response = self.controller.integration_finance_events()

        first_rows = list(
            csv.reader(io.StringIO(first_response.get_data(as_text=True)))
        )
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(
            first_response.headers.get("X-Federation-Export-Mode"), "cursor_page"
        )
        self.assertEqual(first_response.headers.get("X-Federation-Export-Count"), "2")
        self.assertEqual(first_response.headers.get("X-Federation-Has-More"), "true")
        self.assertEqual(first_rows[1][1], "301")
        self.assertEqual(first_rows[2][1], "300")

        second_request = self._make_finance_request(
            finance_service,
            params={
                "limit": "2",
                "cursor": first_response.headers.get("X-Federation-Next-Cursor"),
            },
        )
        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            second_request,
        ), patch.object(
            self.controller,
            "_rate_limit_response",
            return_value=False,
        ), patch.object(
            self.controller,
            "_authenticate",
            return_value=(SimpleNamespace(code=self.partner.code), None),
        ):
            second_response = self.controller.integration_finance_events()

        second_rows = list(
            csv.reader(io.StringIO(second_response.get_data(as_text=True)))
        )
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.headers.get("X-Federation-Has-More"), "false")
        self.assertIsNone(second_response.headers.get("X-Federation-Next-Cursor"))
        self.assertEqual(second_rows[1][1], "299")

    def test_finance_events_route_returns_400_for_invalid_limit(self):
        finance_service = Mock()
        finance_service.sudo.return_value = finance_service
        finance_service.get_handoff_export_batch.side_effect = ValidationError(
            "Finance event export limits must be positive integers."
        )
        request_stub = self._make_finance_request(
            finance_service, params={"limit": "0"}
        )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ), patch.object(
            self.controller,
            "_rate_limit_response",
            return_value=False,
        ), patch.object(
            self.controller,
            "_authenticate",
            return_value=(SimpleNamespace(code=self.partner.code), None),
        ):
            response = self.controller.integration_finance_events()

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.get_data(as_text=True))
        self.assertEqual(payload["error_code"], "data_validation")
        self.assertIn("positive integers", payload["error"])

    def test_finance_events_route_returns_400_for_invalid_cursor(self):
        finance_service = Mock()
        finance_service.sudo.return_value = finance_service
        finance_service.get_handoff_export_batch.side_effect = ValidationError(
            "Finance event export cursors must use the '<timestamp>|<id>' format."
        )
        request_stub = self._make_finance_request(
            finance_service,
            params={"cursor": "not-a-valid-cursor"},
        )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ), patch.object(
            self.controller,
            "_rate_limit_response",
            return_value=False,
        ), patch.object(
            self.controller,
            "_authenticate",
            return_value=(SimpleNamespace(code=self.partner.code), None),
        ):
            response = self.controller.integration_finance_events()

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.get_data(as_text=True))
        self.assertEqual(payload["error_code"], "data_validation")
        self.assertIn("<timestamp>|<id>", payload["error"])

    def test_finance_events_route_reports_effective_page_limit(self):
        event = Mock()
        event.get_handoff_export_row.return_value = [
            "finance_event_v1",
            "501",
            "Bounded Export",
        ]
        finance_service = Mock()
        finance_service.EXPORT_SCHEMA_VERSION = "finance_event_v1"
        finance_service.sudo.return_value = finance_service
        finance_service.get_handoff_export_headers.return_value = [
            "Version",
            "Id",
            "Name",
        ]
        finance_service.get_handoff_export_batch.return_value = {
            "events": [event],
            "count": 1,
            "limit": 500,
            "has_more": False,
            "next_cursor": False,
        }
        request_stub = self._make_finance_request(
            finance_service, params={"limit": "999"}
        )

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ), patch.object(
            self.controller,
            "_rate_limit_response",
            return_value=False,
        ), patch.object(
            self.controller,
            "_authenticate",
            return_value=(SimpleNamespace(code=self.partner.code), None),
        ):
            response = self.controller.integration_finance_events()

        finance_service.get_handoff_export_batch.assert_called_once_with(
            cursor=False,
            limit="999",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Federation-Page-Limit"), "500")

    def test_inbound_route_rate_limits_repeat_callers(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.rate_limit.integration_inbound_deliveries.limit",
            1,
        )
        request_stub = self._make_request(
            headers={
                "X-Federation-Partner-Code": self.partner.code,
                "X-Federation-Partner-Token": self.raw_token,
            },
            json_payload={
                "filename": "clubs.csv",
                "payload_base64": "bmFtZTtjb2RlClN0YWdlZCBDbHViO1NDMDAx",
                "content_type": "text/csv",
            },
        )
        rate_limit_service = self.env["federation.request.rate.limit"].sudo()
        frozen_time = datetime(2026, 4, 18, 12, 0, 0)

        with patch(
            "odoo.addons.sports_federation_import_tools.controllers.integration_api.request",
            request_stub,
        ), patch.object(
            type(rate_limit_service),
            "_get_now",
            return_value=frozen_time,
        ):
            response = self.controller.integration_stage_inbound_delivery(
                self.inbound_contract.code
            )
            blocked = self.controller.integration_stage_inbound_delivery(
                self.inbound_contract.code
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.headers.get("Retry-After"), "60")
        payload = json.loads(blocked.get_data(as_text=True))
        self.assertEqual(payload["error_code"], "retryable_delivery")
