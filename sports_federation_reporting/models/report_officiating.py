from odoo import fields, models


class FederationReportOfficiating(models.Model):
    _name = "federation.report.officiating"
    _description = "Federation Officiating Report"
    _auto = False
    _order = "assignment_count desc, referee_id"

    referee_id = fields.Many2one("federation.referee", string="Referee", readonly=True)
    certification_level = fields.Char(string="Certification Level", readonly=True)
    assignment_count = fields.Integer(string="Assignments", readonly=True)
    completed_assignment_count = fields.Integer(string="Completed", readonly=True)

    def init(self):
        """Create SQL view for officiating report."""
        self.env["federation.report.sql.helper"].recreate_view(
            self._table,
            """
            CREATE VIEW federation_report_officiating AS (
                SELECT
                    row_number() OVER () AS id,
                    r.id AS referee_id,
                    COALESCE(r.certification_level, 'Not Specified') AS certification_level,
                    COUNT(DISTINCT mra.id) AS assignment_count,
                    COUNT(DISTINCT CASE WHEN m.state = 'done' THEN mra.id END) AS completed_assignment_count
                FROM federation_referee r
                LEFT JOIN federation_match_referee mra ON mra.referee_id = r.id
                LEFT JOIN federation_match m ON m.id = mra.match_id
                WHERE r.active = TRUE
                GROUP BY r.id, r.certification_level
            )
            """,
        )
