from odoo import fields, models, tools


class FederationReportClubComplianceSummary(models.Model):
    _name = "federation.report.club.compliance.summary"
    _description = "Club Compliance Summary Report"
    _auto = False
    _order = "compliance_rate, club_id"

    club_id = fields.Many2one("federation.club", string="Club", readonly=True)
    total_checks = fields.Integer(string="Total Checks", readonly=True)
    compliant_count = fields.Integer(string="Compliant", readonly=True)
    non_compliant_count = fields.Integer(string="Non Compliant", readonly=True)
    missing_count = fields.Integer(string="Missing", readonly=True)
    pending_count = fields.Integer(string="Pending", readonly=True)
    expired_count = fields.Integer(string="Expired", readonly=True)
    compliance_rate = fields.Float(string="Compliance Rate (%)", readonly=True)
    remediation_queue_size = fields.Integer(string="Remediation Queue", readonly=True)

    def init(self):
        """Create SQL view for club compliance summary report."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_club_compliance_summary AS (
                SELECT
                    row_number() OVER (ORDER BY cc.club_id) AS id,
                    cc.club_id,
                    COUNT(DISTINCT cc.id) AS total_checks,
                    COUNT(DISTINCT CASE WHEN cc.status = 'compliant' THEN cc.id END)
                        AS compliant_count,
                    COUNT(DISTINCT CASE WHEN cc.status = 'non_compliant' THEN cc.id END)
                        AS non_compliant_count,
                    COUNT(DISTINCT CASE WHEN cc.status = 'missing' THEN cc.id END)
                        AS missing_count,
                    COUNT(DISTINCT CASE WHEN cc.status = 'pending' THEN cc.id END)
                        AS pending_count,
                    COUNT(DISTINCT CASE WHEN cc.status = 'expired' THEN cc.id END)
                        AS expired_count,
                    CASE
                        WHEN COUNT(DISTINCT cc.id) = 0 THEN 0.0
                        ELSE ROUND(
                            100.0
                            * COUNT(DISTINCT CASE WHEN cc.status = 'compliant' THEN cc.id END)
                            / NULLIF(COUNT(DISTINCT cc.id), 0),
                            1
                        )
                    END AS compliance_rate,
                    COUNT(DISTINCT CASE
                        WHEN ds.status IN ('submitted', 'rejected', 'replacement_requested')
                        THEN ds.id
                    END) AS remediation_queue_size
                FROM federation_compliance_check cc
                LEFT JOIN federation_document_submission ds ON ds.club_id = cc.club_id
                WHERE cc.club_id IS NOT NULL
                GROUP BY cc.club_id
            )
        """)
