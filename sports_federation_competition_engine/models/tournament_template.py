from odoo import fields, models
from odoo.exceptions import UserError


class FederationTournamentTemplate(models.Model):
    _name = "federation.tournament.template"
    _description = "Tournament Template"
    _order = "name"

    name = fields.Char(string="Template Name", required=True)
    description = fields.Text(string="Description")
    active = fields.Boolean(default=True)
    line_ids = fields.One2many(
        "federation.tournament.template.line",
        "template_id",
        string="Stages",
    )
    progression_ids = fields.One2many(
        "federation.tournament.template.progression",
        "template_id",
        string="Progression Rules",
    )

    def action_apply(self, tournament):
        """Apply the template to a tournament: create stages, groups, and progressions."""
        self.ensure_one()
        if tournament.stage_ids:
            raise UserError(
                "Tournament already has stages. Clear them first or create a new tournament."
            )

        Stage = self.env["federation.tournament.stage"]
        Group = self.env["federation.tournament.group"]
        Progression = self.env["federation.stage.progression"]

        stage_map = {}  # line sequence → created stage record
        for line in self.line_ids.sorted("sequence"):
            stage = Stage.create(
                {
                    "name": line.stage_name,
                    "tournament_id": tournament.id,
                    "sequence": line.sequence,
                    "stage_type": line.stage_type,
                }
            )
            stage_map[line.id] = stage

            for g in range(line.group_count):
                Group.create(
                    {
                        "name": f"Group {chr(65 + g)}",
                        "stage_id": stage.id,
                        "sequence": g + 1,
                        "max_participants": line.teams_per_group or 0,
                    }
                )

        # Create progression rules
        for rule in self.progression_ids.sorted("sequence"):
            source = stage_map.get(rule.source_line_id.id)
            target = stage_map.get(rule.target_line_id.id)
            if source and target:
                Progression.create(
                    {
                        "tournament_id": tournament.id,
                        "source_stage_id": source.id,
                        "target_stage_id": target.id,
                        "rank_from": rule.rank_from,
                        "rank_to": rule.rank_to,
                        "seeding_method": rule.seeding_method,
                        "auto_advance": rule.auto_advance,
                        "sequence": rule.sequence,
                    }
                )

        return stage_map


class FederationTournamentTemplateLine(models.Model):
    _name = "federation.tournament.template.line"
    _description = "Tournament Template Stage Line"
    _order = "sequence, id"

    template_id = fields.Many2one(
        "federation.tournament.template",
        string="Template",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="Sequence", default=10)
    stage_name = fields.Char(string="Stage Name", required=True)
    stage_type = fields.Selection(
        [
            ("group", "Group Phase"),
            ("knockout", "Knockout"),
            ("final", "Final"),
            ("placement", "Placement"),
        ],
        string="Stage Type",
        default="group",
        required=True,
    )
    format = fields.Selection(
        [
            ("round_robin", "Round Robin"),
            ("knockout", "Knockout"),
        ],
        string="Format",
        default="round_robin",
        required=True,
    )
    group_count = fields.Integer(string="Number of Groups", default=1)
    teams_per_group = fields.Integer(string="Teams per Group")


class FederationTournamentTemplateProgression(models.Model):
    _name = "federation.tournament.template.progression"
    _description = "Tournament Template Progression Rule"
    _order = "sequence, id"

    template_id = fields.Many2one(
        "federation.tournament.template",
        string="Template",
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(string="Sequence", default=10)
    source_line_id = fields.Many2one(
        "federation.tournament.template.line",
        string="Source Stage",
        required=True,
        ondelete="cascade",
        domain="[('template_id', '=', template_id)]",
    )
    target_line_id = fields.Many2one(
        "federation.tournament.template.line",
        string="Target Stage",
        required=True,
        ondelete="cascade",
        domain="[('template_id', '=', template_id)]",
    )
    rank_from = fields.Integer(string="From Rank", default=1)
    rank_to = fields.Integer(string="To Rank", default=2)
    seeding_method = fields.Selection(
        [
            ("keep_rank", "Keep Rank"),
            ("reseed", "Re-seed by Points"),
            ("random", "Random"),
        ],
        string="Seeding Method",
        default="keep_rank",
        required=True,
    )
    auto_advance = fields.Boolean(string="Auto Advance", default=False)
