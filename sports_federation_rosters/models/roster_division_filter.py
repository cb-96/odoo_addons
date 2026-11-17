"""Which players a roster may take: one rule for every picker and for saving.

A player cannot be added to a roster when they are already on it, when the
club team ranking forbids it (see ``club_rank``), or when they are on a roster
of another team of the same club that plays in the same division (tournament)
of the roster's season. Teams in different divisions are not affected, so
playing up between a club's ranked teams keeps working.

The backend roster form and the portal "Add players" page both hide
``unavailable_player_ids``; roster lines enforce the same-division rule on save
(the ranking rule has its own constraint).
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

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

    unavailable_player_ids = fields.Many2many(
        "federation.player",
        compute="_compute_unavailable_player_ids",
        help="Technical: players this roster cannot take (already on it, blocked "
        "by the club team ranking, or on another club team in the same "
        "division).",
    )

    @api.depends(
        "line_ids.player_id",
        "club_rank_blocked_player_ids",
        "same_division_player_ids",
    )
    def _compute_unavailable_player_ids(self):
        for roster in self:
            roster.unavailable_player_ids = (
                roster.line_ids.player_id
                | roster.club_rank_blocked_player_ids
                | roster.same_division_player_ids
            )

    def _unavailable_players(self):
        """The unavailable players of one saved roster, read with full access."""
        self.ensure_one()
        return self.sudo().unavailable_player_ids

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


class FederationTeamRosterLineDivisionRule(models.Model):
    _inherit = "federation.team.roster.line"

    @api.constrains("player_id", "roster_id", "status")
    def _check_same_division_club_team(self):
        for line in self.filtered(lambda item: item.status == "active"):
            roster = line.roster_id
            if line.player_id in roster.sudo().same_division_player_ids:
                raise ValidationError(
                    _(
                        "%(player)s already plays for another team of %(club)s "
                        "in the same division and cannot be added to %(team)s.",
                        player=line.player_id.display_name,
                        club=roster.team_id.club_id.display_name,
                        team=roster.team_id.display_name,
                    )
                )
