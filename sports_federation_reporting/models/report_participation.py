from odoo import fields, models, tools


class FederationReportParticipation(models.Model):
    _name = "federation.report.participation"
    _description = "Federation Participation Report"
    _auto = False
    _order = "season_id, club_id"

    season_id = fields.Many2one("federation.season", string="Season", readonly=True)
    club_id = fields.Many2one("federation.club", string="Club", readonly=True)
    team_count = fields.Integer(string="Teams", readonly=True)
    player_count = fields.Integer(string="Players", readonly=True)
    tournament_count = fields.Integer(string="Tournaments", readonly=True)

    def init(self):
        """Create SQL view for participation report."""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW federation_report_participation AS (
                SELECT
                    row_number() OVER () AS id,
                    s.id AS season_id,
                    c.id AS club_id,
                    COUNT(DISTINCT t.id) AS team_count,
                    COUNT(DISTINCT p.id) AS player_count,
                    COUNT(DISTINCT tn.id) AS tournament_count
                FROM federation_season s
                CROSS JOIN federation_club c
                LEFT JOIN federation_team t ON t.club_id = c.id
                LEFT JOIN federation_player p ON p.club_id = c.id
                LEFT JOIN federation_tournament tn ON tn.season_id = s.id
                WHERE s.active = TRUE AND c.active = TRUE
                GROUP BY s.id, c.id
            )
        """)
