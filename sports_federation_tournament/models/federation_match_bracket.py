from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationMatchBracket(models.Model):
    _inherit = "federation.match"
    _description = "Federation Match – Bracket Wiring"

    bracket_position = fields.Integer(string="Bracket Position")
    resolution_type = fields.Selection(
        [
            ("regulation", "Regulation Score"),
            ("overtime", "Overtime"),
            ("tiebreak", "Tiebreak"),
            ("forfeit", "Forfeit"),
            ("walkover", "Walkover"),
            ("administrative", "Administrative Decision"),
        ],
        string="Resolution",
        default="regulation",
        tracking=True,
        help=(
            "How the advancing team was determined. A tied knockout score must "
            "use a non-regulation resolution and explicitly identify the advancing team."
        ),
    )
    advancing_team_id = fields.Many2one(
        "federation.team",
        string="Advancing Team",
        ondelete="restrict",
        tracking=True,
        help=(
            "Explicit winner used for tied, forfeited, walkover, or "
            "administrative knockout results."
        ),
    )
    bracket_type = fields.Selection(
        [
            ("winners", "Winners"),
            ("losers", "Losers"),
            ("consolation", "Consolation"),
            ("placement_3rd", "3rd Place"),
            ("placement_5th", "5th Place"),
            ("placement_7th", "7th Place"),
        ],
        string="Bracket Type",
    )
    source_match_1_id = fields.Many2one(
        "federation.match",
        string="Source Match 1",
        ondelete="set null",
        help="Winner or loser of this match feeds into the current match.",
    )
    source_match_2_id = fields.Many2one(
        "federation.match", string="Source Match 2", ondelete="set null"
    )
    source_type_1 = fields.Selection(
        [("winner", "Winner"), ("loser", "Loser")],
        string="Source 1 Type",
        default="winner",
    )
    source_type_2 = fields.Selection(
        [("winner", "Winner"), ("loser", "Loser")],
        string="Source 2 Type",
        default="winner",
    )
    next_match_ids = fields.One2many(
        "federation.match", compute="_compute_next_matches", string="Next Matches"
    )

    def _compute_next_matches(self):
        for rec in self:
            rec.next_match_ids = self.search(
                [
                    "|",
                    ("source_match_1_id", "=", rec.id),
                    ("source_match_2_id", "=", rec.id),
                ]
            )

    def _is_bracket_match(self):
        self.ensure_one()
        return bool(
            self.bracket_type
            or self.source_match_1_id
            or self.source_match_2_id
            or self.next_match_ids
        )

    def _validate_completion_result(self):
        super()._validate_completion_result()
        for match in self:
            if not match._is_bracket_match():
                continue
            participants = match.home_team_id | match.away_team_id
            if len(participants) < 2:
                raise ValidationError(
                    _("A knockout match needs both participating teams before it can be completed.")
                )
            if match.advancing_team_id and match.advancing_team_id not in participants:
                raise ValidationError(
                    _("The advancing team must be one of the teams in this knockout match.")
                )
            if match.resolution_type != "regulation" and not match.advancing_team_id:
                raise ValidationError(
                    _("Select the team that advances for this knockout resolution.")
                )
            if match.home_score == match.away_score:
                if match.resolution_type == "regulation":
                    raise ValidationError(
                        _(
                            "A tied knockout match needs an overtime, tiebreak, forfeit, "
                            "walkover, or administrative resolution."
                        )
                    )
            elif match.resolution_type == "regulation" and match.advancing_team_id:
                score_winner = (
                    match.home_team_id
                    if match.home_score > match.away_score
                    else match.away_team_id
                )
                if match.advancing_team_id != score_winner:
                    raise ValidationError(
                        _(
                            "For a regulation result, the advancing team must match "
                            "the winner indicated by the score."
                        )
                    )
        return True

    def _get_result_team(self, result_type):
        self.ensure_one()
        if self.state != "done":
            return False
        if self.advancing_team_id:
            participants = self.home_team_id | self.away_team_id
            if self.advancing_team_id not in participants:
                return False
            if result_type == "winner":
                return self.advancing_team_id
            return (participants - self.advancing_team_id)[:1]
        return super()._get_result_team(result_type)

    def _advance_bracket_teams(self):
        self.ensure_one()
        next_matches = self.search(
            [
                "|",
                ("source_match_1_id", "=", self.id),
                ("source_match_2_id", "=", self.id),
            ]
        )
        for next_match in next_matches:
            if next_match.source_match_1_id == self and not next_match.home_team_id:
                team = self._get_result_team(next_match.source_type_1 or "winner")
                if team:
                    next_match.home_team_id = team
            if next_match.source_match_2_id == self and not next_match.away_team_id:
                team = self._get_result_team(next_match.source_type_2 or "winner")
                if team:
                    next_match.away_team_id = team
