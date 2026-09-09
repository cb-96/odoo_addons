from odoo import fields, models
from odoo.exceptions import ValidationError

from ..services.result_commands import is_result_command_context


class FederationMatchResultControl(models.Model):
    _inherit = "federation.match"

    RESULT_STATE_SELECTION = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("verified", "Verified"),
        ("approved", "Approved"),
        ("contested", "Contested"),
        ("corrected", "Corrected"),
    ]

    result_state = fields.Selection(
        selection=RESULT_STATE_SELECTION,
        string="Result State",
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    result_submitted_by_id = fields.Many2one(
        "res.users",
        string="Submitted By",
        readonly=True,
    )
    result_submitted_on = fields.Datetime(
        string="Submitted On",
        readonly=True,
    )
    result_verified_by_id = fields.Many2one(
        "res.users",
        string="Verified By",
        readonly=True,
    )
    result_verified_on = fields.Datetime(
        string="Verified On",
        readonly=True,
    )
    result_approved_by_id = fields.Many2one(
        "res.users",
        string="Approved By",
        readonly=True,
    )
    result_approved_on = fields.Datetime(
        string="Approved On",
        readonly=True,
    )
    result_contest_reason = fields.Text(
        string="Contest Reason",
    )
    result_correction_reason = fields.Text(
        string="Correction Reason",
    )
    include_in_official_standings = fields.Boolean(
        string="Include in Official Standings",
        default=False,
        tracking=True,
    )
    result_audit_ids = fields.One2many(
        "federation.match.result.audit",
        "match_id",
        string="Result Audit",
    )

    def write(self, vals):
        """Update records with module-specific side effects."""
        if {"home_score", "away_score"} & set(vals) and not self.env.context.get(
            "allow_approved_result_score_write"
        ):
            approved_results = self.filtered(lambda rec: rec.result_state == "approved")
            if approved_results:
                raise ValidationError(
                    "Approved result scores are immutable. Contest or correct the result before editing scores."
                )
        return super().write(vals)

    def _check_result_group(self, group_xmlid, error_message):
        """Validate result group.

        Superuser elevation bypasses the group guard only when the owning result
        command service supplied its process-local authorization token. Raw
        ``sudo()`` is not a result-workflow authorization boundary.
        """
        if self.env.su and is_result_command_context(self.env):
            return
        if not self.env.user.has_group(group_xmlid):
            raise ValidationError(error_message)

    def _recompute_related_standings(self):
        """Handle recompute related standings."""
        Standing = self.env.get("federation.standing")
        if Standing is None:
            return
        Standing = Standing.sudo()

        for rec in self:
            standings = Standing.search([("tournament_id", "=", rec.tournament_id.id)])
            relevant = standings.filtered(
                lambda standing: (
                    not standing.stage_id or standing.stage_id == rec.stage_id
                )
                and (not standing.group_id or standing.group_id == rec.group_id)
            )
            for standing in relevant:
                if standing.state != "frozen":
                    standing.action_recompute()

    def action_open_tournament(self):
        """Open the owning tournament so operators can continue the next step."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_tournament.federation_tournament_action"
        )
        action.update(
            {
                "view_mode": "form",
                "res_id": self.tournament_id.id,
                "domain": [],
            }
        )
        return action

    def _log_result_audit(
        self, event_type, description, from_state, to_state, reason=False
    ):
        """Handle log result audit."""
        Audit = self.env.get("federation.match.result.audit")
        if Audit is None:
            return False
        for rec in self:
            Audit.create_event(
                match=rec,
                event_type=event_type,
                description=description,
                from_state=from_state,
                to_state=to_state,
                reason=reason,
                author=self.env.user,
            )
        return True

    def _result_transition(
        self,
        target_state,
        allowed_from,
        values=None,
        reason=False,
        reason_required=False,
        forbidden_actor_fields=None,
        event_type=False,
        description=False,
    ):
        """Apply shared mechanics while preserving the result-specific audit."""
        results = []
        transition = self.env["federation.workflow.transition"]
        for record in self:
            previous_state = record.result_state
            transition_reason = reason(record) if callable(reason) else reason
            result = transition.execute(
                record,
                target_state,
                allowed_from,
                values=values(record) if callable(values) else values,
                state_field="result_state",
                reason=transition_reason,
                reason_required=reason_required,
                forbidden_actor_fields=forbidden_actor_fields,
                event_type=event_type,
                description=description,
            )
            record._log_result_audit(
                event_type,
                description,
                previous_state,
                target_state,
                reason=transition_reason,
            )
            results.append(result)
        return {
            "record_model": self._name,
            "record_ids": self.ids,
            "current_state": target_state,
            "actor_id": self.env.user.id,
            "results": results,
        }

    def action_submit_result(self):
        """Submit the match result for verification atomically."""
        with self.env.cr.savepoint():
            self._lock_result_transition()
            result = self._result_transition(
                "submitted",
                {"draft", "corrected"},
                values=lambda record: {
                    "result_submitted_by_id": self.env.user.id,
                    "result_submitted_on": fields.Datetime.now(),
                    "result_verified_by_id": False,
                    "result_verified_on": False,
                    "result_approved_by_id": False,
                    "result_approved_on": False,
                },
                event_type="submitted",
                description="Result submitted for verification.",
            )
            for record in self:
                dispatcher = record.env.get("federation.notification.dispatcher")
                if dispatcher is not None:
                    dispatcher.send_result_submitted(record)
            return result

    def _lock_result_transition(self):
        if self.ids:
            self.env.cr.execute(
                "SELECT id FROM federation_match WHERE id = ANY(%s) FOR UPDATE",
                (self.ids,),
            )
            self.invalidate_recordset(
                [
                    "result_state",
                    "result_submitted_by_id",
                    "result_verified_by_id",
                    "result_contest_reason",
                ]
            )

    def action_verify_result(self):
        """Verify submitted results atomically with separation of duties."""
        with self.env.cr.savepoint():
            self._check_result_group(
                "sports_federation_result_control.group_result_validator",
                "Only result validators can verify submitted results.",
            )
            self._lock_result_transition()
            return self._result_transition(
                "verified",
                {"submitted"},
                values=lambda record: {
                    "result_verified_by_id": self.env.user.id,
                    "result_verified_on": fields.Datetime.now(),
                },
                forbidden_actor_fields=("result_submitted_by_id",),
                event_type="verified",
                description="Result verified.",
            )

    def action_approve_result(self):
        """Approve verified results atomically and recompute standings."""
        with self.env.cr.savepoint():
            self._check_result_group(
                "sports_federation_result_control.group_result_approver",
                "Only result approvers can approve verified results.",
            )
            self._lock_result_transition()
            result = self._result_transition(
                "approved",
                {"verified"},
                values=lambda record: {
                    "result_approved_by_id": self.env.user.id,
                    "result_approved_on": fields.Datetime.now(),
                    "include_in_official_standings": True,
                },
                forbidden_actor_fields=(
                    "result_submitted_by_id",
                    "result_verified_by_id",
                ),
                event_type="approved",
                description="Result approved and included in official standings.",
            )
            for record in self:
                dispatcher = record.env.get("federation.notification.dispatcher")
                if dispatcher is not None:
                    dispatcher.send_result_approved(record)
            self._recompute_related_standings()
            return result

    def action_contest_result(self):
        """Contest submitted, verified, or approved results atomically."""
        with self.env.cr.savepoint():
            self._lock_result_transition()
            result = self._result_transition(
                "contested",
                {"submitted", "verified", "approved"},
                values={"include_in_official_standings": False},
                reason=lambda record: record.result_contest_reason,
                reason_required=True,
                event_type="contested",
                description="Result contested.",
            )
            for record in self:
                dispatcher = record.env.get("federation.notification.dispatcher")
                if dispatcher is not None:
                    dispatcher.send_result_contested(record)
            self._recompute_related_standings()
            return result

    def action_raise_dispute_request_exception(self):
        """Unified operator entrypoint for result disputes."""
        return self.action_contest_result()

    def action_correct_result(self):
        """Correct contested or approved results atomically."""
        with self.env.cr.savepoint():
            self._lock_result_transition()
            result = self._result_transition(
                "corrected",
                {"contested", "approved"},
                values={"include_in_official_standings": False},
                reason=lambda record: record.result_correction_reason,
                reason_required=True,
                event_type="corrected",
                description=(
                    "Result corrected and removed from official standings until "
                    "resubmitted."
                ),
            )
            self._recompute_related_standings()
            return result

    def action_reset_result_to_draft(self):
        """Reset controlled results to draft atomically."""
        with self.env.cr.savepoint():
            self._check_result_group(
                "sports_federation_result_control.group_result_approver",
                "Only result approvers can reset results to draft.",
            )
            self._lock_result_transition()
            result = self._result_transition(
                "draft",
                {"submitted", "verified", "approved", "contested", "corrected"},
                values={
                    "include_in_official_standings": False,
                    "result_verified_by_id": False,
                    "result_verified_on": False,
                    "result_approved_by_id": False,
                    "result_approved_on": False,
                },
                event_type="reset",
                description="Result reset to draft.",
            )
            self._recompute_related_standings()
            return result
