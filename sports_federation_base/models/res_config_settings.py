from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    federation_attachment_scan_command = fields.Char(
        string="Attachment Scan Command",
        config_parameter="sports_federation.attachment_scan.command",
        help=(
            "Optional external command that receives upload bytes on stdin. "
            "Exit code 0 accepts the upload, 10 rejects it as infected, and any other "
            "non-zero code rejects it as temporarily unverifiable."
        ),
    )
    federation_attachment_scan_timeout_seconds = fields.Integer(
        string="Attachment Scan Timeout (seconds)",
        config_parameter="sports_federation.attachment_scan.timeout_seconds",
        default=15,
        help="Maximum time to wait for the external attachment scan command.",
    )
