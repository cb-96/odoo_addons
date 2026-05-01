from odoo import fields, models, tools


class FederationReportCompliance(models.Model):
    _name = "federation.report.compliance"
    _description = "Federation Compliance Report"
    _auto = False
    _order = "target_model"

    target_model = fields.Char(string="Target Model", readonly=True)
    compliant_count = fields.Integer(string="Compliant", readonly=True)
    missing_count = fields.Integer(string="Missing", readonly=True)
    pending_count = fields.Integer(string="Pending", readonly=True)
    expired_count = fields.Integer(string="Expired", readonly=True)
    non_compliant_count = fields.Integer(string="Non Compliant", readonly=True)

    def init(self):
        """Create SQL view for compliance report."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_compliance AS (
                SELECT
                    row_number() OVER () AS id,
                    cc.target_model,
                    COUNT(CASE WHEN cc.status = 'compliant' THEN 1 END) AS compliant_count,
                    COUNT(CASE WHEN cc.status = 'missing' THEN 1 END) AS missing_count,
                    COUNT(CASE WHEN cc.status = 'pending' THEN 1 END) AS pending_count,
                    COUNT(CASE WHEN cc.status = 'expired' THEN 1 END) AS expired_count,
                    COUNT(CASE WHEN cc.status = 'non_compliant' THEN 1 END) AS non_compliant_count
                FROM federation_compliance_check cc
                GROUP BY cc.target_model
            )
        """)
