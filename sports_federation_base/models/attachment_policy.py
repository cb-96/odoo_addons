import hashlib
import mimetypes
import os

from odoo import api, models
from odoo.exceptions import ValidationError


class FederationAttachmentPolicy(models.AbstractModel):
    _name = "federation.attachment.policy"
    _description = "Federation Attachment Policy"

    _POLICIES = {
        "integration_inbound_csv": {
            "allowed_extensions": (".csv",),
            "allowed_mimetypes": ("text/csv",),
            "default_mimetype": "text/csv",
            "max_bytes": 5 * 1024 * 1024,
        },
        "portal_document": {
            "allowed_extensions": (".jpeg", ".jpg", ".pdf", ".png"),
            "allowed_mimetypes": (
                "application/pdf",
                "image/jpeg",
                "image/png",
            ),
            "default_mimetype": False,
            "max_bytes": 10 * 1024 * 1024,
        },
    }

    @api.model
    def get_policy(self, policy_code):
        """Return a normalized upload policy definition."""
        policy = self._POLICIES.get(policy_code)
        if not policy:
            raise ValidationError("The selected upload policy is not available.")
        return {
            "allowed_extensions": tuple(sorted(policy["allowed_extensions"])),
            "allowed_mimetypes": tuple(sorted(policy["allowed_mimetypes"])),
            "default_mimetype": policy.get("default_mimetype") or False,
            "max_bytes": policy["max_bytes"],
        }

    @api.model
    def checksum_payload(self, payload):
        """Return a stable checksum for raw bytes."""
        return hashlib.sha256(payload).hexdigest()

    @api.model
    def validate_upload(self, policy_code, filename, payload, mimetype=None):
        """Validate uploaded content against a shared file policy."""
        filename = (filename or "").strip()
        if not filename:
            raise ValidationError("Uploaded files must include a filename.")
        if not payload:
            raise ValidationError("Uploaded files cannot be empty.")

        policy = self.get_policy(policy_code)
        if len(payload) > policy["max_bytes"]:
            max_mebibytes = policy["max_bytes"] // (1024 * 1024)
            raise ValidationError(
                f"Uploaded files must be {max_mebibytes} MiB or smaller."
            )

        extension = os.path.splitext(filename)[1].lower()
        if extension not in policy["allowed_extensions"]:
            allowed_extensions = ", ".join(policy["allowed_extensions"])
            raise ValidationError(
                f"Uploaded files must use one of these extensions: {allowed_extensions}."
            )

        normalized_mimetype = (mimetype or "").split(";", 1)[0].strip().lower()
        if not normalized_mimetype:
            normalized_mimetype = (
                mimetypes.guess_type(filename)[0] or policy["default_mimetype"] or ""
            )
        normalized_mimetype = normalized_mimetype.lower()
        if (
            policy["allowed_mimetypes"]
            and normalized_mimetype not in policy["allowed_mimetypes"]
        ):
            allowed_mimetypes = ", ".join(policy["allowed_mimetypes"])
            raise ValidationError(
                "Uploaded files must use one of these content types: "
                f"{allowed_mimetypes}."
            )

        scan_result = self.env["federation.attachment.scan.service"].scan_upload(
            policy_code,
            filename,
            payload,
            mimetype=normalized_mimetype or policy["default_mimetype"] or False,
        )

        return {
            "filename": filename,
            "payload": payload,
            "checksum": self.checksum_payload(payload),
            "mimetype": normalized_mimetype or policy["default_mimetype"] or False,
            "scan_result": scan_result,
        }
