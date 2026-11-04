from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationMatchFixtureBridge(models.Model):
    _inherit = "federation.match"

    logical_fixture_id = fields.Many2one(
        "federation.fixture",
        string="Logical Fixture",
        readonly=True,
        copy=False,
        ondelete="restrict",
        index=True,
    )

    _unique_logical_fixture = models.Constraint(
        "unique(logical_fixture_id)",
        "A logical fixture can materialize into only one operational match.",
    )

    @api.constrains(
        "logical_fixture_id", "tournament_id", "home_team_id", "away_team_id"
    )
    def _check_logical_fixture_alignment(self):
        for match in self.filtered("logical_fixture_id"):
            fixture = match.logical_fixture_id
            if match.tournament_id != fixture.division_id:
                raise ValidationError(
                    "The operational match must belong to the fixture division."
                )
            if (
                match.home_team_id != fixture.home_team_id
                or match.away_team_id != fixture.away_team_id
            ):
                raise ValidationError(
                    "Operational match participants must match the logical fixture."
                )

    def _sync_logical_fixture_result(self):
        for match in self.filtered("logical_fixture_id"):
            # Result approval is authorized by Result Control, while the
            # logical fixture is intentionally writable only by Format
            # designers. Elevate only this already-linked fixture after the
            # approval command has completed its authorization checks.
            fixture = match.logical_fixture_id.sudo()
            graph_engine = self.env["federation.stage.graph.engine"].sudo()
            if match.result_state == "approved" and match.include_in_official_standings:
                if match._bracket_tie_unresolved():
                    raise ValidationError(
                        "Bracket matches require a winner. Record how the tie was "
                        "decided and the team that advances."
                    )
                fixture.state = "completed"
                graph_engine.resolve_dependants(fixture)
                continue

            if match.result_state in ("contested", "corrected", "draft"):
                applied = fixture.stage_id.outgoing_progression_ids.filtered("applied")
                if applied:
                    raise ValidationError(
                        "This result already fed a later stage. Reopen the progression through an explicit competition correction workflow first."
                    )
                # Undo what this result already decided inside the stage.
                graph_engine.reopen_dependants(fixture)
                fixture.state = "ready"
                if fixture.stage_id.standing_snapshot_id:
                    fixture.stage_id.write(
                        {"standing_snapshot_id": False, "graph_state": "active"}
                    )
                    # The published table showed the withdrawn snapshot.
                    self.env["federation.standing"].sudo().search(
                        [
                            ("structure_stage_id", "=", fixture.stage_id.id),
                            ("state", "=", "frozen"),
                        ]
                    ).write({"state": "computed"})
        return True

    def _bracket_tie_unresolved(self):
        """A tied bracket match without a recorded deciding team."""
        self.ensure_one()
        fixture = self.logical_fixture_id
        if not fixture or fixture.stage_id.stage_type not in ("knockout", "placement"):
            return False
        if self._get_forfeit_winner():
            return False
        if self.home_score != self.away_score:
            return False
        return not (
            self.resolution_type != "regulation"
            and self.advancing_team_id in (self.home_team_id | self.away_team_id)
        )

    def _validate_result_entry(self):
        result = super()._validate_result_entry()
        for match in self:
            if match._bracket_tie_unresolved():
                raise ValidationError(
                    "%s ended in a tie. Select how it was decided (overtime, "
                    "tiebreak, forfeit, ...) and the team that advances before "
                    "submitting." % match.display_name
                )
        return result

    def action_approve_result(self):
        result = super().action_approve_result()
        self._sync_logical_fixture_result()
        return result

    def action_contest_result(self):
        result = super().action_contest_result()
        self._sync_logical_fixture_result()
        return result

    def action_correct_result(self):
        result = super().action_correct_result()
        self._sync_logical_fixture_result()
        return result

    def action_reset_result_to_draft(self):
        result = super().action_reset_result_to_draft()
        self._sync_logical_fixture_result()
        return result


class FederationFixtureBridgeConstraint(models.Model):
    _inherit = "federation.fixture"

    _unique_operational_match = models.Constraint(
        "unique(operational_match_id)",
        "An operational match can belong to only one logical fixture.",
    )

    @api.constrains("operational_match_id")
    def _check_operational_match_backlink(self):
        for fixture in self.filtered("operational_match_id"):
            if fixture.operational_match_id.logical_fixture_id != fixture:
                raise ValidationError(
                    "Fixture and operational match links must reference each other."
                )
