from odoo import api, models

class FederationRoundRobinGenerator(models.AbstractModel):
    _name = "federation.fixture.generator.round.robin"
    _description = "Round-Robin Fixture Generator"

    @api.model
    def generate(self, stage, participants, double=False):
        teams = list(participants.mapped("team_id")); work = teams + [False] if len(teams) % 2 else teams[:]; rounds = []
        for round_index in range(len(work) - 1):
            pairs = []
            for index in range(len(work) // 2):
                first, second = work[index], work[-index - 1]
                if first and second:
                    pairs.append((first, second) if round_index % 2 == 0 else (second, first))
            rounds.append(pairs); work = [work[0], work[-1], *work[1:-1]]
        if double:
            rounds += [[(away, home) for home, away in pairs] for pairs in rounds]
        return self.env["federation.fixture"].create([{"structure_id": stage.structure_id.id, "stage_id": stage.id, "round_number": rn, "sequence": seq * 10, "home_team_id": home.id, "away_team_id": away.id} for rn, pairs in enumerate(rounds, 1) for seq, (home, away) in enumerate(pairs, 1)])
