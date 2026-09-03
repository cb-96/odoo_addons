from odoo import _, api, models
from odoo.exceptions import ValidationError


class FederationDynamicPairing(models.AbstractModel):
    _name = "federation.dynamic.pairing"
    _description = "Dynamic Competition Pairing"

    @api.model
    def swiss_pairs(self, participants, previous_pairs=None, standings=None):
        team_ids = list(participants.mapped("team_id").ids)
        previous = {frozenset(pair) for pair in (previous_pairs or [])}
        points = standings or {}
        ordered = sorted(
            team_ids, key=lambda team_id: (-points.get(team_id, 0), team_id)
        )
        bye = ordered.pop() if len(ordered) % 2 else False
        pairs = []
        while ordered:
            home = ordered.pop(0)
            opponent_index = next(
                (
                    index
                    for index, away in enumerate(ordered)
                    if frozenset((home, away)) not in previous
                ),
                None,
            )
            if opponent_index is None:
                raise ValidationError(
                    _(
                        "No repeat-free Swiss pairing is available for the current score group."
                    )
                )
            pairs.append((home, ordered.pop(opponent_index)))
        return {"pairs": pairs, "bye_team_id": bye}

    @api.model
    def ladder_challenge(self, challenger_rank, opponent_rank, max_distance=3):
        if challenger_rank <= opponent_rank:
            raise ValidationError(
                _("A ladder challenge must target a higher-ranked opponent.")
            )
        if challenger_rank - opponent_rank > max_distance:
            raise ValidationError(
                _("The opponent is outside the allowed challenge distance.")
            )
        return {
            "allowed": True,
            "winner_rank": opponent_rank,
            "loser_rank": challenger_rank,
        }

    @api.model
    def double_elimination_routes(self, participant_count):
        participant_count = int(participant_count or 0)
        if participant_count < 4 or participant_count & (participant_count - 1):
            raise ValidationError(
                _(
                    "Double elimination requires a power-of-two field of at least four teams."
                )
            )
        winners_rounds = participant_count.bit_length() - 1
        losers_rounds = 2 * winners_rounds - 2
        return {
            "winner_bracket_matches": participant_count - 1,
            "loser_bracket_matches": participant_count - 2,
            "grand_final_matches": 2,
            "winner_bracket_rounds": winners_rounds,
            "loser_bracket_rounds": losers_rounds,
        }
