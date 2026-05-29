import csv
import io
import logging

from odoo import http
from odoo.addons.sports_federation_base.exceptions import (
    AttachmentScanVerificationError,
)
from odoo.addons.sports_federation_base.request_security import (
    FederationRequestSecurityMixin,
)
from odoo.exceptions import AccessError, ValidationError
from odoo.http import Response, request

from .integration_api_auth_mixin import FederationIntegrationApiAuthMixin
from .integration_api_response_mixin import FederationIntegrationApiResponseMixin

_logger = logging.getLogger(__name__)


class FederationIntegrationApi(
    FederationRequestSecurityMixin,
    FederationIntegrationApiResponseMixin,
    FederationIntegrationApiAuthMixin,
    http.Controller,
):
    @property
    def _request_proxy(self):
        """Expose the module-level request object behind a stable controller hook."""
        return request

    @http.route(
        ["/integration/v1/contracts"],
        type="http",
        auth="public",
        website=False,
        methods=["GET"],
        csrf=False,
    )
    def integration_contracts(self, **kw):
        """Handle integration contracts."""
        blocked_response = self._rate_limit_response("integration_contracts")
        if blocked_response:
            return blocked_response
        try:
            partner, _subscription = self._authenticate()
        except (AccessError, ValidationError) as error:
            return self._json_error_response(status=401, error=error)

        subscriptions = partner.subscription_ids.filtered(
            lambda line: line.state == "active" and line.contract_id.active
        )
        return self._json_response(
            {
                "partner": {
                    "code": partner.code,
                    "name": partner.name,
                },
                "contracts": [
                    line.contract_id.build_manifest_payload(subscription=line)
                    for line in subscriptions
                ],
            }
        )

    @http.route(
        ["/integration/v1/outbound/finance/events"],
        type="http",
        auth="public",
        website=False,
        methods=["GET"],
        csrf=False,
    )
    def integration_finance_events(self, **kw):
        """Handle integration finance events."""
        blocked_response = self._rate_limit_response("integration_finance_events")
        if blocked_response:
            return blocked_response
        try:
            partner, _subscription = self._authenticate(
                contract_code="finance_event_v1"
            )
        except (AccessError, ValidationError) as error:
            return self._json_error_response(status=401, error=error)

        FinanceEvent = request.env.get("federation.finance.event")
        if FinanceEvent is None:
            return self._json_error_response(
                status=404,
                detail="The finance export contract is not available in this database.",
                default_category="configuration_error",
            )

        export_cursor = (request.params.get("cursor") or "").strip() or False
        export_limit = (request.params.get("limit") or "").strip() or False
        try:
            export_batch = FinanceEvent.sudo().get_handoff_export_batch(
                cursor=export_cursor,
                limit=export_limit,
            )
            events = export_batch["events"]
        except ValidationError as error:
            return self._json_error_response(status=400, error=error)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(FinanceEvent.get_handoff_export_headers())
        for event in events:
            writer.writerow(event.get_handoff_export_row())

        headers = [
            (
                "Content-Disposition",
                'attachment; filename="finance_events_partner_handoff.csv"',
            ),
            ("X-Federation-Contract", "finance_event_v1"),
            ("X-Federation-Contract-Version", FinanceEvent.EXPORT_SCHEMA_VERSION),
            ("X-Federation-Partner-Code", partner.code),
            ("X-Federation-Export-Mode", "cursor_page"),
            ("X-Federation-Export-Count", str(export_batch["count"])),
            (
                "X-Federation-Has-More",
                "true" if export_batch["has_more"] else "false",
            ),
            ("X-Federation-Page-Limit", str(export_batch["limit"])),
        ]
        if export_batch["next_cursor"]:
            headers.append(("X-Federation-Next-Cursor", export_batch["next_cursor"]))

        return Response(
            output.getvalue(),
            content_type="text/csv; charset=utf-8",
            headers=headers,
        )

    @http.route(
        ["/integration/v1/inbound/<string:contract_code>/deliveries"],
        type="http",
        auth="public",
        website=False,
        methods=["POST"],
        csrf=False,
    )
    def integration_stage_inbound_delivery(self, contract_code, **kw):
        """Handle integration stage inbound delivery."""
        blocked_response = self._rate_limit_response("integration_inbound_deliveries")
        if blocked_response:
            return blocked_response
        request_proxy = self._request_proxy
        try:
            partner, subscription = self._authenticate(contract_code=contract_code)
            payload = request_proxy.httprequest.get_json(silent=True) or {}
            if not isinstance(payload, dict):
                raise ValidationError(
                    "Inbound delivery requests must use a JSON object body."
                )

            request_idempotency_key = self._get_idempotency_key()

            delivery_result = (
                request_proxy.env["federation.integration.delivery"]
                .sudo()
                .stage_partner_delivery_result(
                    partner=partner,
                    contract=subscription.contract_id,
                    filename=(payload.get("filename") or "").strip(),
                    payload_base64=(payload.get("payload_base64") or "").strip(),
                    content_type=(payload.get("content_type") or "").strip() or False,
                    notes=(payload.get("notes") or "").strip() or False,
                    source_reference=(payload.get("source_reference") or "").strip()
                    or False,
                    idempotency_key=request_idempotency_key,
                )
            )
            delivery = delivery_result["delivery"]
        except AccessError as error:
            return self._json_error_response(status=401, error=error)
        except ValidationError as error:
            return self._json_error_response(status=400, error=error)
        except AttachmentScanVerificationError as error:
            return self._json_error_response(
                status=503,
                error=error,
                default_category="retryable_delivery",
            )
        except Exception as error:
            _logger.exception(
                "Inbound delivery staging failed for contract %s", contract_code
            )
            return self._json_error_response(status=500, error=error)

        headers = [("X-Federation-Delivery-Outcome", delivery_result["outcome"])]
        if request_idempotency_key:
            headers.extend(
                [
                    (
                        "X-Federation-Idempotency-Key",
                        delivery_result["idempotency_key"] or request_idempotency_key,
                    ),
                    (
                        "X-Federation-Idempotent-Replay",
                        "true" if delivery_result["replayed"] else "false",
                    ),
                ]
            )

        return self._json_response(
            {
                "delivery_outcome": delivery_result["outcome"],
                "delivery": {
                    "id": delivery.id,
                    "name": delivery.name,
                    "partner_code": delivery.partner_id.code,
                    "contract_code": delivery.contract_id.code,
                    "state": delivery.state,
                    "filename": delivery.filename,
                    "idempotency_key": delivery.idempotency_key,
                    "payload_checksum": delivery.payload_checksum,
                    "route_hint": delivery.contract_id.route_hint,
                },
            },
            status=201,
            headers=headers,
        )
