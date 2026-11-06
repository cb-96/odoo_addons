"""League tables that show a format stage.

A ``federation.standing`` linked to a structure stage is the published, live
view of that stage. Its rows come from the stage graph engine, so the table on
the website, the frozen stage snapshot and progression to the next stage use
the same numbers. Freezing either side freezes both.
"""

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationStandingStage(models.Model):
    _inherit = "federation.standing"

    structure_stage_id = fields.Many2one(
        "federation.structure.stage",
        string="Competition Stage",
        readonly=True,
        ondelete="cascade",
        index=True,
        help="Stage whose results this table shows. Set automatically for "
        "competitions built in the Competition Hub.",
    )

    def _scope_match_domain(self):
        self.ensure_one()
        if not self.structure_stage_id:
            return super()._scope_match_domain()
        return [
            ("logical_fixture_id.stage_id", "=", self.structure_stage_id.id),
            ("state", "!=", "cancelled"),
            ("home_team_id", "!=", False),
            ("away_team_id", "!=", False),
        ]

    def _get_relevant_matches(self):
        self.ensure_one()
        if not self.structure_stage_id:
            return super()._get_relevant_matches()
        return self.env["federation.match"].search(
            self._scope_match_domain()
            + [("state", "=", "done"), ("include_in_official_standings", "=", True)]
        )

    def _get_participants(self):
        self.ensure_one()
        if not self.structure_stage_id:
            return super()._get_participants()
        teams = self.structure_stage_id.stage_participant_ids.mapped("team_id")
        return self.env["federation.tournament.participant"].search(
            [
                ("tournament_id", "=", self.tournament_id.id),
                ("team_id", "in", teams.ids),
            ]
        )

    def action_recompute(self):
        linked = self.filtered("structure_stage_id")
        if self - linked:
            super(FederationStandingStage, self - linked).action_recompute()
        engine = self.env["federation.stage.graph.engine"]
        Line = self.env["federation.standing.line"]
        for record in linked:
            if record.state == "frozen" and not self.env.context.get("force_recompute"):
                raise ValidationError(
                    _(
                        "Cannot recompute a frozen standing. "
                        "Use force_recompute context to override."
                    )
                )
            participant_by_team = {
                participant.team_id.id: participant
                for participant in record._get_participants()
            }
            record.line_ids.unlink()
            for row in engine._standings(record.structure_stage_id):
                participant = participant_by_team.get(row["team"].id)
                if not participant:
                    continue
                Line.create(
                    {
                        "standing_id": record.id,
                        "participant_id": participant.id,
                        "rank": row["rank"],
                        "played": row["played"],
                        "won": row["won"],
                        "drawn": row["drawn"],
                        "lost": row["lost"],
                        "score_for": row["score_for"],
                        "score_against": row["score_against"],
                        "points": row["points"],
                        "tiebreak_notes": row.get("tiebreak_notes") or "",
                    }
                )
            record.write({"state": "computed", "computed_on": fields.Datetime.now()})
        return True

    def action_freeze(self):
        linked = self.filtered("structure_stage_id")
        if self.env.context.get("stage_engine_freeze"):
            # Called by the engine after it froze the stage snapshot.
            linked.with_context(force_recompute=True).action_recompute()
            return super().action_freeze()
        if self - linked:
            super(FederationStandingStage, self - linked).action_freeze()
        for record in linked:
            stage = record.structure_stage_id
            if stage.graph_state == "frozen":
                record.with_context(stage_engine_freeze=True).action_freeze()
            else:
                if not stage.has_access("write"):
                    raise ValidationError(
                        _(
                            "Freezing %(table)s also decides the next stage. Ask a "
                            "competition designer to freeze it."
                        )
                        % {"table": record.display_name}
                    )
                # Freezing the stage also applies progression to the next stage.
                stage.action_freeze_standings()
        return True

    def action_unfreeze(self):
        for record in self.filtered("structure_stage_id"):
            stage = record.structure_stage_id
            if stage.outgoing_progression_ids.filtered("applied"):
                raise ValidationError(
                    _(
                        "This table already decided who plays in the next stage. "
                        "Correct the next stage before unfreezing."
                    )
                )
            if stage.standing_snapshot_id:
                stage.write({"standing_snapshot_id": False, "graph_state": "active"})
        return super().action_unfreeze()
