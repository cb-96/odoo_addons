from odoo import _, api, models
from odoo.exceptions import ValidationError

class FederationStageGraphValidator(models.AbstractModel):
    _name = "federation.stage.graph.validator"
    _description = "Stage Graph Validator"

    @api.model
    def validate(self, structure):
        adjacency = {stage.id: [] for stage in structure.stage_ids}
        progressions = self.env["federation.structure.stage.progression"].search([("structure_id", "=", structure.id), ("active", "=", True)])
        for progression in progressions:
            adjacency[progression.source_stage_id.id].append(progression.target_stage_id.id)
        visiting, completed = set(), set()
        def visit(stage_id):
            if stage_id in visiting:
                raise ValidationError(_("Stage graph contains a cycle."))
            if stage_id in completed:
                return
            visiting.add(stage_id)
            for target_id in adjacency.get(stage_id, []):
                visit(target_id)
            visiting.remove(stage_id); completed.add(stage_id)
        for stage in structure.stage_ids:
            visit(stage.id)
        return True
