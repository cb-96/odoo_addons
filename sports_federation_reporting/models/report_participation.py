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
                    row_number() OVER (ORDER BY s.id, c.id) AS id,
                    s.id AS season_id,
                    c.id AS club_id,
                    (
                        SELECT COUNT(*)
                        FROM federation_team t
                        WHERE t.club_id = c.id
                    ) AS team_count,
                    (
                        SELECT COUNT(*)
                        FROM federation_player p
                        WHERE p.club_id = c.id
                    ) AS player_count,
                    (
                        SELECT COUNT(*)
                        FROM federation_tournament tn
                        WHERE tn.season_id = s.id
                    ) AS tournament_count
                FROM federation_season s
                CROSS JOIN federation_club c
                WHERE s.active = TRUE AND c.active = TRUE
            )
        """)
