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

        def build_pairs(remaining):
            if not remaining:
                return []
            home = remaining[0]
            for index, away in enumerate(remaining[1:], 1):
                if frozenset((home, away)) in previous:
                    continue
                rest = remaining[1:index] + remaining[index + 1 :]
                pairs = build_pairs(rest)
                if pairs is not None:
                    return [(home, away), *pairs]
            return None

        pairs = build_pairs(ordered)
        if pairs is None:
            raise ValidationError(
                _(
                    "No repeat-free Swiss pairing is available for the current score group."
                )
            )
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
