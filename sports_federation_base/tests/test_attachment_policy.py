import subprocess
from unittest.mock import patch

from odoo.addons.sports_federation_base.exceptions import (
    AttachmentScanVerificationError,
)
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestFederationAttachmentPolicy(TransactionCase):
    def test_settings_round_trip_attachment_scan_parameters(self):
        settings = self.env["res.config.settings"].create(
            {
                "federation_attachment_scan_command": "/usr/local/bin/scan-upload",
                "federation_attachment_scan_timeout_seconds": 27,
            }
        )

        settings.execute()

        params = self.env["ir.config_parameter"].sudo()
        self.assertEqual(
            params.get_param("sports_federation.attachment_scan.command"),
            "/usr/local/bin/scan-upload",
        )
        self.assertEqual(
            params.get_param("sports_federation.attachment_scan.timeout_seconds"),
            "27",
        )

        reloaded = self.env["res.config.settings"].create({})
        self.assertEqual(
            reloaded.federation_attachment_scan_command,
            "/usr/local/bin/scan-upload",
        )
        self.assertEqual(reloaded.federation_attachment_scan_timeout_seconds, 27)

    def test_validate_upload_skips_scan_when_no_hook_is_configured(self):
        upload = self.env["federation.attachment.policy"].validate_upload(
            "portal_document",
            "club-insurance.pdf",
            b"portal-payload",
            mimetype="application/pdf",
        )

        self.assertEqual(upload["scan_result"]["status"], "skipped")
        self.assertEqual(upload["scan_result"]["provider"], "disabled")

    def test_validate_upload_runs_external_hook_when_configured(self):
        scanner = self.env["federation.attachment.scan.service"]
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.attachment_scan.command",
            "/usr/local/bin/fake-attachment-scan",
        )

        with patch.object(
            type(scanner),
            "_run_external_hook",
            return_value={
                "status": "clean",
                "provider": "external_command",
                "detail": "clean",
            },
        ) as mocked_hook:
            upload = self.env["federation.attachment.policy"].validate_upload(
                "integration_inbound_csv",
                "clubs.csv",
                b"name;code\nClub;CL001",
                mimetype="text/csv",
            )

        mocked_hook.assert_called_once_with(
            "/usr/local/bin/fake-attachment-scan",
            "integration_inbound_csv",
            "clubs.csv",
            b"name;code\nClub;CL001",
            mimetype="text/csv",
        )
        self.assertEqual(upload["scan_result"]["status"], "clean")

    def test_validate_upload_blocks_when_hook_reports_malware(self):
        scanner = self.env["federation.attachment.scan.service"]
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.attachment_scan.command",
            "/usr/local/bin/fake-attachment-scan",
        )

        with patch.object(
            type(scanner),
            "_run_external_hook",
            side_effect=ValidationError(
                "Uploaded files failed the federation malware scan."
            ),
        ):
            with self.assertRaises(ValidationError) as error:
                self.env["federation.attachment.policy"].validate_upload(
                    "portal_document",
                    "club-insurance.pdf",
                    b"portal-payload",
                    mimetype="application/pdf",
                )

        self.assertIn("malware scan", str(error.exception))

    def test_scan_upload_returns_clean_result_from_external_command(self):
        scanner = self.env["federation.attachment.scan.service"]
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.attachment_scan.command",
            "/usr/local/bin/fake-attachment-scan",
        )

        with patch(
            "odoo.addons.sports_federation_base.models.attachment_scan_service.subprocess.run"
        ) as mocked_run:
            mocked_run.return_value = subprocess.CompletedProcess(
                args=["/usr/local/bin/fake-attachment-scan"],
                returncode=0,
                stdout=b"clean\n",
                stderr=b"",
            )

            result = scanner.scan_upload(
                "portal_document",
                "club-insurance.pdf",
                b"portal-payload",
                mimetype="application/pdf",
            )

        self.assertEqual(result["status"], "clean")
        self.assertEqual(result["detail"], "clean")
        self.assertEqual(
            mocked_run.call_args.kwargs["env"]["SF_ATTACHMENT_POLICY"],
            "portal_document",
        )
        self.assertEqual(
            mocked_run.call_args.kwargs["env"]["SF_ATTACHMENT_FILENAME"],
            "club-insurance.pdf",
        )
        self.assertEqual(
            mocked_run.call_args.kwargs["env"]["SF_ATTACHMENT_MIMETYPE"],
            "application/pdf",
        )

    def test_scan_upload_blocks_infected_payloads_from_external_command(self):
        scanner = self.env["federation.attachment.scan.service"]
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.attachment_scan.command",
            "/usr/local/bin/fake-attachment-scan",
        )

        with patch(
            "odoo.addons.sports_federation_base.models.attachment_scan_service.subprocess.run"
        ) as mocked_run:
            mocked_run.return_value = subprocess.CompletedProcess(
                args=["/usr/local/bin/fake-attachment-scan"],
                returncode=10,
                stdout=b"infected\n",
                stderr=b"",
            )

            with self.assertRaises(ValidationError) as error:
                scanner.scan_upload(
                    "portal_document",
                    "club-insurance.pdf",
                    b"portal-payload",
                    mimetype="application/pdf",
                )

        self.assertIn("malware scan", str(error.exception))

    def test_scan_upload_rejects_when_external_command_cannot_verify(self):
        scanner = self.env["federation.attachment.scan.service"]
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.attachment_scan.command",
            "/usr/local/bin/fake-attachment-scan",
        )

        with patch(
            "odoo.addons.sports_federation_base.models.attachment_scan_service.subprocess.run"
        ) as mocked_run:
            mocked_run.return_value = subprocess.CompletedProcess(
                args=["/usr/local/bin/fake-attachment-scan"],
                returncode=2,
                stdout=b"",
                stderr=b"scanner offline\n",
            )

            with self.assertRaises(AttachmentScanVerificationError) as error:
                scanner.scan_upload(
                    "integration_inbound_csv",
                    "clubs.csv",
                    b"name;code\nClub;CL001",
                    mimetype="text/csv",
                )

        self.assertIn("could not be verified", str(error.exception))

    def test_scan_upload_rejects_when_external_command_is_unavailable(self):
        scanner = self.env["federation.attachment.scan.service"]
        self.env["ir.config_parameter"].sudo().set_param(
            "sports_federation.attachment_scan.command",
            "/usr/local/bin/fake-attachment-scan",
        )

        with patch(
            "odoo.addons.sports_federation_base.models.attachment_scan_service.subprocess.run",
            side_effect=FileNotFoundError(),
        ):
            with self.assertRaises(AttachmentScanVerificationError) as error:
                scanner.scan_upload(
                    "portal_document",
                    "club-insurance.pdf",
                    b"portal-payload",
                    mimetype="application/pdf",
                )

        self.assertIn("could not be verified", str(error.exception))
