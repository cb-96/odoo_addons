from odoo import fields, models


class FederationMatchBracket(models.Model):
    _inherit = "federation.match"
    _description = "Federation Match – Bracket Wiring"

    bracket_position = fields.Integer(string="Bracket Position")
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
        "federation.match",
        string="Source Match 2",
        ondelete="set null",
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
        "federation.match",
        compute="_compute_next_matches",
        string="Next Matches",
    )

    def _compute_next_matches(self):
        """Compute next matches."""
        for rec in self:
            rec.next_match_ids = self.search(
                [
                    "|",
                    ("source_match_1_id", "=", rec.id),
                    ("source_match_2_id", "=", rec.id),
                ]
            )

    def _advance_bracket_teams(self):
        """After a match is done, populate next bracket matches automatically."""
        self.ensure_one()
        if self.home_score == self.away_score:
            return  # draw — no automatic advancement

        next_matches = self.search(
            [
                "|",
                ("source_match_1_id", "=", self.id),
                ("source_match_2_id", "=", self.id),
            ]
        )
        for nm in next_matches:
            if nm.source_match_1_id == self and not nm.home_team_id:
                team = self._get_result_team(nm.source_type_1 or "winner")
                if team:
                    nm.home_team_id = team
            if nm.source_match_2_id == self and not nm.away_team_id:
                team = self._get_result_team(nm.source_type_2 or "winner")
                if team:
                    nm.away_team_id = team
