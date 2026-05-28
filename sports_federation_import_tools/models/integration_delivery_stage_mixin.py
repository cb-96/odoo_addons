import base64
import binascii
import hashlib

from odoo import api, models
from odoo.exceptions import ValidationError


class FederationIntegrationDeliveryStageMixin(models.AbstractModel):
    _name = "federation.integration.delivery.stage.mixin"
    _description = "Federation Integration Delivery Staging Helpers"

    DELIVERY_OUTCOME_CREATED = "created"
    DELIVERY_OUTCOME_CHECKSUM_REUSE = "checksum_reuse"
    DELIVERY_OUTCOME_IDEMPOTENCY_REPLAY = "idempotency_replay"

    @api.model
    def _normalize_idempotency_key(self, idempotency_key):
        """Return a normalized idempotency key or False."""
        return (idempotency_key or "").strip() or False

    @api.model
    def _build_idempotency_fingerprint(
        self,
        filename,
        payload_checksum,
        mimetype=None,
        source_reference=None,
    ):
        """Build a stable request fingerprint for idempotent replay checks."""
        return hashlib.sha256(
            "\x1f".join(
                [
                    filename or "",
                    payload_checksum or "",
                    mimetype or "",
                    source_reference or "",
                ]
            ).encode("utf-8")
        ).hexdigest()

    @api.model
    def _match_idempotent_delivery(
        self,
        partner,
        contract,
        idempotency_key,
        idempotency_fingerprint,
    ):
        """Return the existing delivery for a matching idempotency key."""
        if not idempotency_key:
            return self.browse()

        existing = self.sudo().search(
            [
                ("partner_id", "=", partner.id),
                ("contract_id", "=", contract.id),
                ("idempotency_key", "=", idempotency_key),
            ],
            limit=1,
        )
        if not existing:
            return self.browse()
        if existing.idempotency_fingerprint != idempotency_fingerprint:
            raise ValidationError(
                "This idempotency key has already been used for a different inbound delivery request."
            )
        return existing

    @api.model
    def _decode_partner_payload(self, payload_base64):
        """Decode the inbound payload and reject malformed base64 content."""
        try:
            return base64.b64decode(payload_base64, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValidationError(
                "Inbound payload must be valid base64-encoded content."
            ) from error

    @api.model
    def _validate_partner_payload_upload(self, filename, payload, content_type=None):
        """Apply the shared attachment policy to the inbound upload."""
        return self.env["federation.attachment.policy"].validate_upload(
            "integration_inbound_csv",
            filename,
            payload,
            mimetype=content_type,
        )

    @api.model
    def _find_duplicate_payload_delivery(self, partner, contract, checksum):
        """Return an active delivery already staging the same payload checksum."""
        return self.sudo().search(
            [
                ("partner_id", "=", partner.id),
                ("contract_id", "=", contract.id),
                ("payload_checksum", "=", checksum),
                ("state", "in", self.ACTIVE_DEDUPLICATION_STATES),
            ],
            limit=1,
        )

    @api.model
    def _reuse_staged_payload(
        self,
        existing,
        normalized_idempotency_key,
        idempotency_fingerprint,
    ):
        """Reuse an already-staged payload and attach idempotency metadata if missing."""
        if normalized_idempotency_key:
            if (
                existing.idempotency_key
                and existing.idempotency_key != normalized_idempotency_key
            ):
                raise ValidationError(
                    "This payload is already staged under a different inbound idempotency key."
                )
            if not existing.idempotency_key:
                existing.write(
                    {
                        "idempotency_key": normalized_idempotency_key,
                        "idempotency_fingerprint": idempotency_fingerprint,
                    }
                )
        return {
            "delivery": existing,
            "replayed": True,
            "idempotency_key": existing.idempotency_key or normalized_idempotency_key,
            "outcome": self.DELIVERY_OUTCOME_CHECKSUM_REUSE,
        }

    @api.model
    def _create_staged_delivery(
        self,
        partner,
        contract,
        filename,
        payload_base64,
        upload,
        checksum,
        normalized_idempotency_key,
        idempotency_fingerprint,
        notes,
        source_reference,
    ):
        """Create the delivery record plus its payload attachment."""
        delivery = self.sudo().create(
            {
                "partner_id": partner.id,
                "contract_id": contract.id,
                "filename": filename,
                "payload_checksum": checksum,
                "idempotency_key": normalized_idempotency_key,
                "idempotency_fingerprint": idempotency_fingerprint,
                "source_reference": source_reference,
                "notes": notes,
            }
        )
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .create(
                {
                    "name": upload["filename"],
                    "datas": payload_base64,
                    "res_model": delivery._name,
                    "res_id": delivery.id,
                    "mimetype": upload["mimetype"],
                }
            )
        )
        delivery.write({"attachment_id": attachment.id})
        return {
            "delivery": delivery,
            "replayed": False,
            "idempotency_key": delivery.idempotency_key or normalized_idempotency_key,
            "outcome": self.DELIVERY_OUTCOME_CREATED,
        }

    @api.model
    def stage_partner_delivery(
        self,
        partner,
        contract,
        filename,
        payload_base64,
        content_type=None,
        notes=None,
        source_reference=None,
        idempotency_key=None,
    ):
        """Stage a partner delivery and return only the delivery record."""
        return self.stage_partner_delivery_result(
            partner=partner,
            contract=contract,
            filename=filename,
            payload_base64=payload_base64,
            content_type=content_type,
            notes=notes,
            source_reference=source_reference,
            idempotency_key=idempotency_key,
        )["delivery"]

    @api.model
    def stage_partner_delivery_result(
        self,
        partner,
        contract,
        filename,
        payload_base64,
        content_type=None,
        notes=None,
        source_reference=None,
        idempotency_key=None,
    ):
        """Stage a partner delivery and return replay plus outcome metadata."""
        if not partner:
            raise ValidationError(
                "Select a partner before staging an inbound delivery."
            )
        if not contract or contract.direction != "inbound":
            raise ValidationError(
                "The selected contract does not accept inbound deliveries."
            )
        if not filename:
            raise ValidationError("Inbound deliveries require a filename.")
        if not payload_base64:
            raise ValidationError(
                "Inbound deliveries require a base64-encoded payload."
            )

        payload = self._decode_partner_payload(payload_base64)
        upload = self._validate_partner_payload_upload(
            filename,
            payload,
            content_type=content_type,
        )
        checksum = upload["checksum"]
        normalized_idempotency_key = self._normalize_idempotency_key(idempotency_key)
        idempotency_fingerprint = False
        if normalized_idempotency_key:
            idempotency_fingerprint = self._build_idempotency_fingerprint(
                filename=upload["filename"],
                payload_checksum=checksum,
                mimetype=upload["mimetype"],
                source_reference=source_reference,
            )
            existing = self._match_idempotent_delivery(
                partner=partner,
                contract=contract,
                idempotency_key=normalized_idempotency_key,
                idempotency_fingerprint=idempotency_fingerprint,
            )
            if existing:
                return {
                    "delivery": existing,
                    "replayed": True,
                    "idempotency_key": existing.idempotency_key
                    or normalized_idempotency_key,
                    "outcome": self.DELIVERY_OUTCOME_IDEMPOTENCY_REPLAY,
                }

        existing = self._find_duplicate_payload_delivery(partner, contract, checksum)
        if existing:
            return self._reuse_staged_payload(
                existing,
                normalized_idempotency_key,
                idempotency_fingerprint,
            )

        return self._create_staged_delivery(
            partner=partner,
            contract=contract,
            filename=filename,
            payload_base64=payload_base64,
            upload=upload,
            checksum=checksum,
            normalized_idempotency_key=normalized_idempotency_key,
            idempotency_fingerprint=idempotency_fingerprint,
            notes=notes,
            source_reference=source_reference,
        )
