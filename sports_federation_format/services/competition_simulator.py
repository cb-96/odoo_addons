import random

from odoo import _, api, models
from odoo.exceptions import ValidationError


class FederationCompetitionSimulator(models.AbstractModel):
    _name = "federation.competition.simulator"
    _description = "Competition Structure Simulator"

    @api.model
    def validate_structure(self, structure):
        self.env["federation.stage.graph.validator"].validate(structure)
        issues = []
        stages = structure.stage_ids
        for stage in stages:
            incoming = stage.incoming_progression_ids.filtered("active")
            if stage.source_type == "progression" and not incoming:
                issues.append(_("Stage %(stage)s has no incoming progression.", stage=stage.display_name))
            for progression in stage.outgoing_progression_ids.filtered("active"):
                if progression.rank_to - progression.rank_from + 1 < 1:
                    issues.append(_("Progression from %(stage)s selects no teams.", stage=stage.display_name))
        unreachable = stages.filtered(lambda stage: stage.source_type == "progression" and not stage.incoming_progression_ids)
        if unreachable:
            issues.append(_("The graph contains unreachable stages."))
        return {"valid": not issues, "issues": issues}

    @api.model
    def simulate(self, structure, seed=1):
        validation = self.validate_structure(structure)
        if not validation["valid"]:
            raise ValidationError("\n".join(validation["issues"]))
        rng = random.Random(seed)
        results = []
        for fixture in structure.fixture_ids.sorted(lambda item: (item.round_number, item.sequence, item.id)):
            if fixture.bye_team_id:
                continue
            results.append(
                {
                    "fixture_id": fixture.id,
                    "home_score": rng.randint(0, 5),
                    "away_score": rng.randint(0, 5),
                }
            )
        return {"seed": seed, "fixture_count": len(results), "results": results}
