from odoo import fields, models


class FederationRetentionEvidence(models.Model):
    _name = 'federation.retention.evidence'
    _description = 'Retention Execution Evidence'
    _order = 'started_on desc, id desc'

    policy = fields.Char(required=True, index=True)
    started_on = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    completed_on = fields.Datetime(required=True, default=fields.Datetime.now)
    deleted_count = fields.Integer(required=True, default=0)
    skipped_count = fields.Integer(required=True, default=0)
    attachment_count = fields.Integer(required=True, default=0)
    status = fields.Selection([('passed', 'Passed'), ('failed', 'Failed')], required=True, index=True)
    operator_message = fields.Text()
    correlation_id = fields.Char(index=True)
