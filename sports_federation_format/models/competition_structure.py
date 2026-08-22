from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationCompetitionStructure(models.Model):
    _name = "federation.competition.structure"
    _description = "Competition Structure Version"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "version desc,id desc"
    name = fields.Char(required=True)
    edition_id = fields.Many2one(
        "federation.competition.edition", required=True, ondelete="cascade", index=True
    )
    division_id = fields.Many2one(
        "federation.tournament", required=True, ondelete="cascade", index=True
    )
    participant_set_id = fields.Many2one(
        "federation.participant.set", required=True, ondelete="restrict"
    )
    version = fields.Integer(default=1, required=True)
    format_type = fields.Selection(
        [
            ("single_round_robin", "League"),
            ("double_round_robin", "Double League"),
            ("knockout", "Knockout Cup"),
            ("pool_knockout", "Pools then Knockout"),
            ("custom", "Custom"),
        ],
        required=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("generated", "Generated"),
            ("frozen", "Frozen"),
            ("superseded", "Superseded"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    stage_ids = fields.One2many("federation.structure.stage", "structure_id")
    fixture_ids = fields.One2many("federation.fixture", "structure_id", readonly=True)
    _unique_version = models.Constraint(
        "unique(division_id,version)", "Structure versions must be unique per division."
    )

    def action_generate(self):
        for rec in self:
            roots = rec.stage_ids.filtered(lambda stage: not stage.incoming_progression_ids)
            if not roots:
                raise ValidationError("Add at least one root stage.")
            self.env["federation.stage.graph.engine"].validate_graph(rec)
            for stage in roots:
                stage.action_prepare_stage()
            rec.state = "generated"
        return True

    def action_validate_graph(self):
        for rec in self:
            self.env["federation.stage.graph.engine"].validate_graph(rec)
        return True

    def action_freeze(self):
        for rec in self:
            if not rec.fixture_ids:
                raise ValidationError(
                    "Generate fixtures before freezing the structure."
                )
            rec.state = "frozen"
            self.env["federation.competition.event"].emit(
                rec,
                "competition_structure_frozen",
                {"fixture_count": len(rec.fixture_ids), "version": rec.version},
            )
        return True


class FederationStructureStage(models.Model):
    _name = "federation.structure.stage"
    _description = "Competition Structure Stage"
    _order = "sequence,id"
    name = fields.Char(required=True)
    structure_id = fields.Many2one(
        "federation.competition.structure",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10, required=True)
    stage_type = fields.Selection(
        [
            ("league", "League"),
            ("pool", "Pool"),
            ("knockout", "Knockout"),
            ("placement", "Placement"),
        ],
        required=True,
    )


class FederationFixture(models.Model):
    _name = "federation.fixture"
    _description = "Logical Competition Fixture"
    _order = "stage_id,round_number,sequence,id"
    name = fields.Char(compute="_compute_name", store=True)
    structure_id = fields.Many2one(
        "federation.competition.structure",
        required=True,
        ondelete="cascade",
        index=True,
    )
    edition_id = fields.Many2one(
        related="structure_id.edition_id", store=True, index=True
    )
    division_id = fields.Many2one(
        related="structure_id.division_id", store=True, index=True
    )
    stage_id = fields.Many2one(
        "federation.structure.stage", required=True, ondelete="cascade", index=True
    )
    round_number = fields.Integer(required=True, index=True)
    sequence = fields.Integer(default=10)
    home_team_id = fields.Many2one("federation.team", ondelete="restrict", index=True)
    away_team_id = fields.Many2one("federation.team", ondelete="restrict", index=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("ready", "Ready"),
            ("cancelled", "Cancelled"),
            ("completed", "Completed"),
        ],
        default="ready",
        required=True,
        index=True,
    )

    @api.depends("home_team_id", "away_team_id")
    def _compute_name(self):
        for r in self:
            r.name = f"{r.home_team_id.display_name or 'TBD'} vs {r.away_team_id.display_name or 'TBD'}"
