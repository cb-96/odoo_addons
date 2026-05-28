from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class FederationStageProgression(models.Model):
    _name = "federation.stage.progression"
    _description = "Stage Progression Rule"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "sequence, id"

    name = fields.Char(string="Name", compute="_compute_name", store=True)
    tournament_id = fields.Many2one(
        "federation.tournament",
        string="Tournament",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(string="Sequence", default=10)

    # Source
    source_stage_id = fields.Many2one(
        "federation.tournament.stage",
        string="Source Stage",
        required=True,
        ondelete="cascade",
        domain="[('tournament_id', '=', tournament_id)]",
    )
    source_group_id = fields.Many2one(
        "federation.tournament.group",
        string="Source Group",
        ondelete="cascade",
        domain="[('stage_id', '=', source_stage_id)]",
        help="Leave empty for cross-group ranking (all groups in the source stage).",
    )

    # Target
    target_stage_id = fields.Many2one(
        "federation.tournament.stage",
        string="Target Stage",
        required=True,
        ondelete="cascade",
        domain="[('tournament_id', '=', tournament_id)]",
    )
    target_group_id = fields.Many2one(
        "federation.tournament.group",
        string="Target Group",
        ondelete="cascade",
        domain="[('stage_id', '=', target_stage_id)]",
    )

    # Rank selection
    rank_from = fields.Integer(
        string="From Rank",
        required=True,
        default=1,
        help="Lowest rank to include (e.g. 1 = winner).",
    )
    rank_to = fields.Integer(
        string="To Rank",
        required=True,
        default=2,
        help="Highest rank to include (e.g. 2 = top 2 advance).",
    )
    cross_group = fields.Boolean(
        string="Cross-Group Ranking",
        compute="_compute_cross_group",
        store=True,
        help="When source group is empty, ranks are compared across all groups in the stage.",
    )

    # Seeding in target
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
    auto_advance = fields.Boolean(
        string="Auto Advance",
        default=False,
        help="Automatically advance teams when standings are frozen.",
    )
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("executed", "Executed"),
        ],
        string="Status",
        default="pending",
        required=True,
    )

    @api.depends("source_stage_id", "target_stage_id", "rank_from", "rank_to")
    def _compute_name(self):
        """Compute name."""
        for rec in self:
            parts = []
            if rec.source_stage_id:
                parts.append(rec.source_stage_id.name or "?")
            parts.append(f"rank {rec.rank_from}-{rec.rank_to}")
            parts.append("→")
            if rec.target_stage_id:
                parts.append(rec.target_stage_id.name or "?")
            rec.name = " ".join(parts)

    @api.depends("source_group_id")
    def _compute_cross_group(self):
        """Compute cross group."""
        for rec in self:
            rec.cross_group = not rec.source_group_id

    @api.constrains("rank_from", "rank_to")
    def _check_ranks(self):
        """Validate ranks."""
        for rec in self:
            if rec.rank_from < 1:
                raise ValidationError("From Rank must be at least 1.")
            if rec.rank_to < rec.rank_from:
                raise ValidationError("To Rank must be >= From Rank.")

    @api.constrains("source_stage_id", "target_stage_id")
    def _check_not_same_stage(self):
        """Validate not same stage."""
        for rec in self:
            if rec.source_stage_id == rec.target_stage_id:
                raise ValidationError("Source and target stages must be different.")

    def action_execute(self):
        """Execute the progression: read standings and advance teams."""
        import random as _random

        for rec in self:
            if rec.state == "executed":
                raise UserError("This progression rule has already been executed.")

            qualified = rec._get_qualified_teams()
            if not qualified:
                raise UserError("No qualified teams found. Compute standings first.")

            # Apply seeding
            if rec.seeding_method == "random":
                _random.shuffle(qualified)
            elif rec.seeding_method == "reseed":
                qualified.sort(
                    key=lambda x: (-x["points"], -x["score_diff"], x["name"])
                )
            # keep_rank: already sorted by rank

            Participant = self.env["federation.tournament.participant"]
            existing_target_participants = Participant.search(
                [
                    ("tournament_id", "=", rec.tournament_id.id),
                    ("stage_id", "=", rec.target_stage_id.id),
                    (
                        "group_id",
                        "=",
                        rec.target_group_id.id if rec.target_group_id else False,
                    ),
                ]
            )
            next_seed = max(existing_target_participants.mapped("seed") or [0]) + 1
            for idx, entry in enumerate(qualified):
                team = entry["team"]
                # Find existing participant or create
                existing = Participant.search(
                    [
                        ("tournament_id", "=", rec.tournament_id.id),
                        ("team_id", "=", team.id),
                    ],
                    limit=1,
                )
                vals = {
                    "stage_id": rec.target_stage_id.id,
                    "group_id": rec.target_group_id.id or False,
                    "seed": next_seed + idx,
                    "state": "confirmed",
                }
                if existing:
                    existing.write(vals)
                else:
                    vals.update(
                        {
                            "tournament_id": rec.tournament_id.id,
                            "team_id": team.id,
                        }
                    )
                    Participant.create(vals)

            rec.state = "executed"

    def _get_qualified_teams(self):
        """Get teams from standings that match the rank range.

        Returns a list of dicts: [{"team": team_record, "rank": int, "points": int, ...}]
        """
        self.ensure_one()
        Standing = self.env["federation.standing"]

        if self.source_group_id:
            # Single group — read standings for that group
            standings = Standing.search(
                [
                    ("tournament_id", "=", self.tournament_id.id),
                    ("stage_id", "=", self.source_stage_id.id),
                    ("group_id", "=", self.source_group_id.id),
                    ("state", "in", ("computed", "frozen")),
                ],
                limit=1,
            )
            if not standings:
                return []
            lines = standings.line_ids.filtered(
                lambda ln: self.rank_from <= ln.rank <= self.rank_to
            ).sorted("rank")
            return [
                {
                    "team": ln.team_id,
                    "rank": ln.rank,
                    "points": ln.points,
                    "score_diff": ln.score_diff,
                    "name": ln.team_id.name,
                }
                for ln in lines
            ]
        else:
            # Cross-group: collect the specified rank range across ALL groups in the stage.
            # Also handles the no-group case (standings with group_id = False).
            groups = self.env["federation.tournament.group"].search(
                [
                    ("stage_id", "=", self.source_stage_id.id),
                ]
            )
            all_entries = []

            def _extract_lines(standing_rec):
                return standing_rec.line_ids.filtered(
                    lambda ln: self.rank_from <= ln.rank <= self.rank_to
                ).sorted("rank")

            def _to_entry(ln):
                return {
                    "team": ln.team_id,
                    "rank": ln.rank,
                    "points": ln.points,
                    "score_diff": ln.score_diff,
                    "name": ln.team_id.name,
                }

            if groups:
                for group in groups:
                    standings = Standing.search(
                        [
                            ("tournament_id", "=", self.tournament_id.id),
                            ("stage_id", "=", self.source_stage_id.id),
                            ("group_id", "=", group.id),
                            ("state", "in", ("computed", "frozen")),
                        ],
                        limit=1,
                    )
                    if not standings:
                        continue
                    all_entries.extend(_to_entry(ln) for ln in _extract_lines(standings))

            # Fallback (and no-group case): also check for stage-level standings
            # (group_id = False). This handles stages without group splits, or
            # tournaments where standings were computed at stage level rather than
            # group level.
            if not all_entries:
                standings = Standing.search(
                    [
                        ("tournament_id", "=", self.tournament_id.id),
                        ("stage_id", "=", self.source_stage_id.id),
                        ("group_id", "=", False),
                        ("state", "in", ("computed", "frozen")),
                    ],
                    limit=1,
                )
                if standings:
                    all_entries.extend(_to_entry(ln) for ln in _extract_lines(standings))

            # Sort cross-group by points desc, then goal diff desc, then name asc
            all_entries.sort(key=lambda x: (-x["points"], -x["score_diff"], x["name"]))
            return all_entries
