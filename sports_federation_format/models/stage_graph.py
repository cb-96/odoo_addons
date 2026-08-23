from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationStructureStage(models.Model):
    _inherit = "federation.structure.stage"
    format_type = fields.Selection(
        [
            ("single_round_robin", "Single Round Robin"),
            ("double_round_robin", "Double Round Robin"),
            ("knockout", "Knockout"),
            ("placement_bracket", "Full Placement Bracket"),
            ("manual", "Manual"),
        ],
        default="single_round_robin",
        required=True,
    )
    source_type = fields.Selection(
        [
            ("registration", "Finalized Registration"),
            ("progression", "Previous Stage Progression"),
            ("manual", "Manual"),
        ],
        default="registration",
        required=True,
    )
    carryover_policy = fields.Selection(
        [
            ("none", "None"),
            ("same_group_results", "Results Between Advancing Teams"),
            ("full_points", "Complete Source Standings"),
        ],
        default="none",
        required=True,
    )
    graph_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("waiting", "Waiting"),
            ("ready", "Ready"),
            ("active", "Active"),
            ("frozen", "Standings Frozen"),
            ("completed", "Completed"),
        ],
        default="draft",
        required=True,
        index=True,
    )
    final_rank_from = fields.Integer()
    final_rank_to = fields.Integer()
    stage_participant_ids = fields.One2many("federation.stage.participant", "stage_id")
    stage_fixture_ids = fields.One2many("federation.fixture", "stage_id")
    incoming_progression_ids = fields.One2many(
        "federation.structure.stage.progression", "target_stage_id"
    )
    outgoing_progression_ids = fields.One2many(
        "federation.structure.stage.progression", "source_stage_id"
    )
    standing_snapshot_id = fields.Many2one(
        "federation.stage.standing.snapshot", readonly=True, copy=False
    )
    standing_line_ids = fields.One2many(
        related="standing_snapshot_id.line_ids", readonly=True
    )

    def action_prepare_stage(self):
        for rec in self:
            self.env["federation.stage.graph.engine"].prepare_stage(rec)
        return True

    def action_start_stage(self):
        for rec in self:
            if rec.graph_state != "ready":
                raise ValidationError("Only ready stages can start.")
            rec.graph_state = "active"
        return True

    def action_freeze_standings(self):
        for rec in self:
            self.env["federation.stage.graph.engine"].freeze_standings(rec)
        return True


class FederationFixture(models.Model):
    _inherit = "federation.fixture"
    home_source_fixture_id = fields.Many2one("federation.fixture", ondelete="set null")
    home_source_outcome = fields.Selection([("winner", "Winner"), ("loser", "Loser")])
    away_source_fixture_id = fields.Many2one("federation.fixture", ondelete="set null")
    away_source_outcome = fields.Selection([("winner", "Winner"), ("loser", "Loser")])
    operational_match_id = fields.Many2one(
        "federation.match",
        string="Operational Match",
        readonly=True,
        copy=False,
        ondelete="restrict",
        index=True,
    )
    home_score = fields.Integer(
        related="operational_match_id.home_score", readonly=True
    )
    away_score = fields.Integer(
        related="operational_match_id.away_score", readonly=True
    )
    result_state = fields.Selection(
        related="operational_match_id.result_state", readonly=True
    )
    include_in_official_standings = fields.Boolean(
        related="operational_match_id.include_in_official_standings", readonly=True
    )
    bye_team_id = fields.Many2one(
        "federation.team", readonly=True, copy=False, ondelete="restrict"
    )
    placement_from = fields.Integer()
    placement_to = fields.Integer()

    def action_materialize_match(self):
        """Create or return the single operational match for each playable fixture."""
        return self.env["federation.fixture.materializer"].materialize(self)

    def action_approve_result(self):
        raise ValidationError(
            "Fixture results are read-only. Submit, verify and approve the operational match through Result Control."
        )

    def unlink(self):
        if self.filtered("operational_match_id"):
            raise ValidationError(
                "Fixtures with operational matches cannot be deleted. Cancel or supersede the competition structure instead."
            )
        return super().unlink()


class FederationStageParticipant(models.Model):
    _name = "federation.stage.participant"
    _description = "Stage Participant"
    _order = "seed,id"
    stage_id = fields.Many2one(
        "federation.structure.stage", required=True, ondelete="cascade", index=True
    )
    team_id = fields.Many2one(
        "federation.team", required=True, ondelete="restrict", index=True
    )
    seed = fields.Integer(required=True)
    source_rank = fields.Integer()
    carried_points = fields.Integer()
    carried_played = fields.Integer()
    carried_score_for = fields.Integer()
    carried_score_against = fields.Integer()
    _uniq_team = models.Constraint(
        "unique(stage_id,team_id)", "A team occurs once per stage."
    )
    _uniq_seed = models.Constraint(
        "unique(stage_id,seed)", "Stage seeds must be unique."
    )


class FederationStageProgression(models.Model):
    _name = "federation.structure.stage.progression"
    _description = "Competition Structure Stage Progression"
    _order = "source_stage_id,rank_from,id"
    structure_id = fields.Many2one(
        related="source_stage_id.structure_id", store=True, index=True
    )
    name = fields.Char(required=True)
    source_stage_id = fields.Many2one(
        "federation.structure.stage", required=True, ondelete="cascade", index=True
    )
    target_stage_id = fields.Many2one(
        "federation.structure.stage", required=True, ondelete="cascade", index=True
    )
    rank_from = fields.Integer(default=1, required=True)
    rank_to = fields.Integer(default=1, required=True)
    target_seed_from = fields.Integer(default=1, required=True)
    active = fields.Boolean(default=True)
    applied = fields.Boolean(readonly=True)

    @api.constrains("source_stage_id", "target_stage_id", "rank_from", "rank_to")
    def _check(self):
        for r in self:
            if (
                r.source_stage_id == r.target_stage_id
                or r.source_stage_id.structure_id != r.target_stage_id.structure_id
            ):
                raise ValidationError(
                    "Progression must connect different stages in one structure."
                )
            if r.rank_from < 1 or r.rank_to < r.rank_from:
                raise ValidationError("Invalid rank range.")


class FederationStageStandingSnapshot(models.Model):
    _name = "federation.stage.standing.snapshot"
    _description = "Frozen Stage Standings"
    stage_id = fields.Many2one(
        "federation.structure.stage", required=True, ondelete="restrict", index=True
    )
    frozen_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    frozen_by_id = fields.Many2one(
        "res.users", default=lambda s: s.env.user, readonly=True
    )
    line_ids = fields.One2many(
        "federation.stage.standing.line", "snapshot_id", readonly=True
    )

    def unlink(self):
        raise ValidationError("Frozen standings are immutable.")


class FederationStageStandingLine(models.Model):
    _name = "federation.stage.standing.line"
    _description = "Frozen Stage Standing"
    _order = "rank,id"
    snapshot_id = fields.Many2one(
        "federation.stage.standing.snapshot",
        required=True,
        ondelete="cascade",
        index=True,
    )
    team_id = fields.Many2one("federation.team", required=True, ondelete="restrict")
    rank = fields.Integer(required=True)
    played = fields.Integer()
    won = fields.Integer()
    drawn = fields.Integer()
    lost = fields.Integer()
    score_for = fields.Integer()
    score_against = fields.Integer()
    points = fields.Integer()
