import logging
import os
import shlex
import subprocess

from odoo import api, models
from odoo.addons.sports_federation_base.exceptions import (
    AttachmentScanVerificationError,
)
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class FederationAttachmentScanService(models.AbstractModel):
    _name = "federation.attachment.scan.service"
    _description = "Federation Attachment Scan Service"

    @api.model
    def _get_scan_command(self):
        """Return the configured external scan command, if any."""
        return (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("sports_federation.attachment_scan.command")
            or ""
        ).strip()

    @api.model
    def _get_timeout_seconds(self):
        """Return the scan timeout with a safe integer fallback."""
        raw_timeout = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(
                "sports_federation.attachment_scan.timeout_seconds",
                default="15",
            )
        )
        try:
            timeout_seconds = int(raw_timeout)
        except (TypeError, ValueError):
            timeout_seconds = 15
        return max(timeout_seconds, 1)

    @api.model
    def _build_scan_environment(self, policy_code, filename, mimetype=None):
        """Expose stable metadata to external scanning hooks."""
        environment = os.environ.copy()
        environment.update(
            {
                "SF_ATTACHMENT_POLICY": policy_code,
                "SF_ATTACHMENT_FILENAME": filename,
                "SF_ATTACHMENT_MIMETYPE": mimetype or "",
            }
        )
        return environment

    @api.model
    def _extract_hook_detail(self, result):
        """Return the first non-empty output line from the external hook."""
        for output in (result.stdout or b"", result.stderr or b""):
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            for line in output.splitlines():
                detail = line.strip()
                if detail:
                    return detail
        return ""

    @api.model
    def _build_verification_error(self):
        """Return the stable operator-facing verification failure."""
        return AttachmentScanVerificationError(
            "Uploaded files could not be verified by the federation malware scanner. Try again later."
        )

    @api.model
    def _run_external_hook(
        self, command, policy_code, filename, payload, mimetype=None
    ):
        """Run the configured external command against the raw upload bytes."""
        try:
            result = subprocess.run(
                shlex.split(command),
                input=payload,
                capture_output=True,
                check=False,
                env=self._build_scan_environment(
                    policy_code, filename, mimetype=mimetype
                ),
                timeout=self._get_timeout_seconds(),
            )
        except (FileNotFoundError, PermissionError):
            _logger.exception("Attachment scanner command is unavailable: %s", command)
            raise self._build_verification_error()
        except subprocess.TimeoutExpired:
            _logger.warning(
                "Attachment scanner command timed out for %s under policy %s.",
                filename,
                policy_code,
            )
            raise self._build_verification_error()

        detail = self._extract_hook_detail(result)
        if result.returncode == 0:
            return {
                "status": "clean",
                "provider": "external_command",
                "detail": detail or False,
            }

        if result.returncode == 10:
            _logger.warning(
                "Attachment scanner blocked %s under policy %s: %s",
                filename,
                policy_code,
                detail or "malware_detected",
            )
            raise ValidationError("Uploaded files failed the federation malware scan.")

        _logger.warning(
            "Attachment scanner command failed for %s under policy %s with code %s: %s",
            filename,
            policy_code,
            result.returncode,
            detail or "no detail provided",
        )
        raise self._build_verification_error()

    @api.model
    def scan_upload(self, policy_code, filename, payload, mimetype=None):
        """Return the scan result for an upload or skip when no hook is configured."""
        command = self._get_scan_command()
        if not command:
            return {
                "status": "skipped",
                "provider": "disabled",
                "detail": False,
            }
        return self._run_external_hook(
            command,
            policy_code,
            filename,
            payload,
            mimetype=mimetype,
        )
