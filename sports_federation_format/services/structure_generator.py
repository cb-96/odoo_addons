from odoo import _, api, models
from odoo.exceptions import ValidationError


class FederationStructureGenerator(models.AbstractModel):
    _name = "federation.structure.generator"
    _description = "Pure Competition Structure Generator"

    @api.model
    def preview(self, participant_set, format_type):
        teams = list(
            participant_set.line_ids.sorted(
                lambda x: (x.seed or 9999, x.team_id.name or "", x.id)
            ).mapped("team_id")
        )
        if len(teams) < 2:
            raise ValidationError(
                _("At least two finalized participants are required.")
            )
        if format_type not in ("single_round_robin", "double_round_robin"):
            raise ValidationError(
                _(
                    "The first V2 release supports league fixture generation; knockout formats remain explicit structures."
                )
            )
        work = teams[:]
        bye = False
        if len(work) % 2:
            work.append(bye)
        rounds = []
        for rnd in range(len(work) - 1):
            pairs = []
            for i in range(len(work) // 2):
                a, b = work[i], work[-i - 1]
                if a and b:
                    pairs.append((a, b) if rnd % 2 == 0 else (b, a))
            rounds.append(pairs)
            work = [work[0], work[-1], *work[1:-1]]
        if format_type == "double_round_robin":
            rounds += [[(b, a) for a, b in pairs] for pairs in rounds]
        return rounds

    @api.model
    def generate(self, structure):
        structure.ensure_one()
        if structure.state == "frozen":
            raise ValidationError(_("A frozen structure cannot be regenerated."))
        if structure.fixture_ids:
            structure.fixture_ids.unlink()
        stage = structure.stage_ids[:1] or self.env[
            "federation.structure.stage"
        ].create(
            {
                "name": _("League Phase"),
                "structure_id": structure.id,
                "sequence": 10,
                "stage_type": "league",
            }
        )
        rounds = self.preview(structure.participant_set_id, structure.format_type)
        vals = []
        for number, pairs in enumerate(rounds, 1):
            for seq, (home, away) in enumerate(pairs, 1):
                vals.append(
                    {
                        "structure_id": structure.id,
                        "stage_id": stage.id,
                        "round_number": number,
                        "sequence": seq * 10,
                        "home_team_id": home.id,
                        "away_team_id": away.id,
                    }
                )
        self.env["federation.fixture"].create(vals)
        structure.state = "generated"
        return True
