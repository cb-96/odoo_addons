from odoo import fields, models, tools


class FederationReportOfficiatingCoverage(models.Model):
    _name = "federation.report.officiating.coverage"
    _description = "Referee Assignment Coverage Report"
    _auto = False
    _order = "coverage_pct, tournament_id"

    tournament_id = fields.Many2one(
        "federation.tournament", string="Tournament", readonly=True
    )
    total_matches = fields.Integer(string="Total Matches", readonly=True)
    covered_matches = fields.Integer(string="Covered Matches", readonly=True)
    uncovered_matches = fields.Integer(string="Uncovered Matches", readonly=True)
    coverage_pct = fields.Float(string="Coverage (%)", readonly=True)

    def init(self):
        """Create SQL view for officiating coverage per tournament."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_officiating_coverage AS (
                SELECT
                    row_number() OVER (ORDER BY m.tournament_id) AS id,
                    m.tournament_id,
                    COUNT(DISTINCT m.id) AS total_matches,
                    COUNT(DISTINCT CASE WHEN mra.id IS NOT NULL THEN m.id END)
                        AS covered_matches,
                    COUNT(DISTINCT CASE WHEN mra.id IS NULL THEN m.id END)
                        AS uncovered_matches,
                    CASE
                        WHEN COUNT(DISTINCT m.id) = 0 THEN 0.0
                        ELSE ROUND(
                            100.0
                            * COUNT(DISTINCT CASE WHEN mra.id IS NOT NULL THEN m.id END)
                            / NULLIF(COUNT(DISTINCT m.id), 0),
                            1
                        )
                    END AS coverage_pct
                FROM federation_match m
                LEFT JOIN federation_match_referee mra
                    ON mra.match_id = m.id AND mra.state != 'cancelled'
                WHERE m.state != 'cancelled'
                GROUP BY m.tournament_id
            )
        """)
