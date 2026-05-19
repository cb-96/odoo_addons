from odoo import fields, models


class FederationAuditNote(models.Model):
    _name = "federation.audit.note"
    _description = "Federation Audit Note"
    _order = "created_on desc, id"

    request_id = fields.Many2one(
        "federation.override.request",
        string="Request",
        required=True,
        ondelete="cascade",
    )
    note = fields.Text(string="Note", required=True)
    author_id = fields.Many2one(
        "res.users",
        string="Author",
        default=lambda self: self.env.user,
        required=True,
    )
    created_on = fields.Datetime(
        string="Created On",
        default=fields.Datetime.now,
        required=True,
    )
