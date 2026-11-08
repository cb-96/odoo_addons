"""Keep a club's teams in the same division from sharing players.

A player who is on a roster of another team of the same club, where both teams
play in the same division (tournament) of the roster's season, is not offered
in this roster's player picker. Teams in different divisions are not affected,
so playing up between a club's ranked teams keeps working.
"""

from odoo import api, fields, models

INACTIVE_PARTICIPANT_STATES = ("withdrawn", "cancelled", "rejected")


class FederationTeamRosterDivisionFilter(models.Model):
    _inherit = "federation.team.roster"

    same_division_player_ids = fields.Many2many(
        "federation.player",
        compute="_compute_same_division_player_ids",
        help="Technical: players on a roster of another team of the same club "
        "that plays in the same division this season.",
    )

    def _club_division_teams(self):
        """Other teams of the club that share a division with this roster's team."""
        self.ensure_one()
        team = self.team_id
        Participant = self.env["federation.tournament.participant"].sudo()
        if not team or not team.club_id or not self.season_id:
            return self.env["federation.team"]
        active = [("state", "not in", INACTIVE_PARTICIPANT_STATES)]
        divisions = Participant.search(
            [
                ("team_id", "=", team.id),
                ("tournament_id.season_id", "=", self.season_id.id),
            ]
            + active
        ).tournament_id
        if not divisions:
            return self.env["federation.team"]
        return Participant.search(
            [
                ("tournament_id", "in", divisions.ids),
                ("team_id.club_id", "=", team.club_id.id),
                ("team_id", "!=", team.id),
            ]
            + active
        ).team_id

    @api.depends("team_id", "season_id")
    def _compute_same_division_player_ids(self):
        Line = self.env["federation.team.roster.line"].sudo()
        for roster in self:
            players = self.env["federation.player"]
            teams = roster._club_division_teams()
            if teams:
                players = Line.search(
                    [
                        ("roster_id.team_id", "in", teams.ids),
                        ("roster_id.season_id", "=", roster.season_id.id),
                        ("roster_id.status", "!=", "closed"),
                        ("status", "=", "active"),
                    ]
                ).player_id
            roster.same_division_player_ids = players
