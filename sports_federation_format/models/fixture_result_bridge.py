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
            fixture = match.logical_fixture_id
            if match.result_state == "approved" and match.include_in_official_standings:
                if (
                    fixture.stage_id.stage_type in ("knockout", "placement")
                    and match.home_score == match.away_score
                ):
                    raise ValidationError("Bracket matches require a winner.")
                fixture.state = "completed"
                self.env["federation.stage.graph.engine"].resolve_dependants(fixture)
                continue

            if match.result_state in ("contested", "corrected", "draft"):
                applied = fixture.stage_id.outgoing_progression_ids.filtered("applied")
                if applied:
                    raise ValidationError(
                        "This result already fed a later stage. Reopen the progression through an explicit competition correction workflow first."
                    )
                fixture.state = "ready"
                if fixture.stage_id.standing_snapshot_id:
                    fixture.stage_id.write(
                        {"standing_snapshot_id": False, "graph_state": "active"}
                    )
        return True

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
