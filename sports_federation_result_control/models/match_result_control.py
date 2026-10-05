from odoo import _, api, fields, models
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
    score_entry_confirmed = fields.Boolean(
        string="Scores Entered and Checked",
        help=(
            "Confirms that both score fields were deliberately entered before "
            "submission."
        ),
    )
    zero_zero_confirmed = fields.Boolean(
        string="Confirm 0–0 Result",
        help="Required when both aggregate scores are zero.",
    )
    result_period_ids = fields.One2many(
        "federation.match.result.period",
        "match_id",
        string="Set / Period Scores",
    )

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for incoming in vals_list:
            vals = dict(incoming)
            if {"home_score", "away_score"} & set(vals):
                vals.setdefault("score_entry_confirmed", True)
            prepared.append(vals)
        return super().create(prepared)

    @api.constrains("home_score", "away_score")
    def _check_non_negative_scores(self):
        for match in self:
            if match.home_score < 0 or match.away_score < 0:
                raise ValidationError(_("Scores cannot be negative."))

    def _validate_result_entry(self):
        for match in self:
            if not match.score_entry_confirmed:
                raise ValidationError(
                    _("Enter and check both scores before submitting the result.")
                )
            if (
                match.home_score == 0
                and match.away_score == 0
                and not match.zero_zero_confirmed
            ):
                raise ValidationError(
                    _(
                        "Both scores are 0. Confirm that 0–0 is the intended "
                        "result before submitting."
                    )
                )
            if match.result_period_ids:
                home_total = sum(match.result_period_ids.mapped("home_score"))
                away_total = sum(match.result_period_ids.mapped("away_score"))
                if (home_total, away_total) != (match.home_score, match.away_score):
                    raise ValidationError(
                        _(
                            "Set / period totals are %(period_home)s–%(period_away)s, "
                            "but the aggregate result is %(home)s–%(away)s. Align "
                            "them before submitting.",
                            period_home=home_total,
                            period_away=away_total,
                            home=match.home_score,
                            away=match.away_score,
                        )
                    )
        return True

    def write(self, vals):
        """Update records with module-specific side effects."""
        protected_score_fields = {
            "home_score",
            "away_score",
            "score_entry_confirmed",
            "zero_zero_confirmed",
        }
        score_fields_changed = bool(protected_score_fields & set(vals))
        if score_fields_changed and not self.env.context.get(
            "allow_approved_result_score_write"
        ):
            approved_results = self.filtered(lambda rec: rec.result_state == "approved")
            if approved_results:
                raise ValidationError(
                    "Approved result scores are immutable. Contest or correct the result before editing scores."
                )
        if score_fields_changed:
            vals = dict(vals)
            vals.setdefault("score_entry_confirmed", True)
            vals.setdefault("zero_zero_confirmed", False)
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

    def _competition_workflow_edition(self):
        self.ensure_one()
        # Workflow policy flags are internal configuration; result operators
        # need them even when they cannot read the edition directly.
        tournament = self.tournament_id.sudo()
        if tournament and tournament.edition_id:
            return tournament.edition_id.sudo()
        return self.env["federation.competition.edition"]

    def action_submit_result(self):
        """Submit the match result for verification atomically."""
        with self.env.cr.savepoint():
            self._lock_result_transition()
            self._validate_result_entry()
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
            editions = self.mapped(lambda match: match._competition_workflow_edition())
            if editions and not any(edition.result_verification_required for edition in editions):
                self.with_context(workflow_policy_bypass=True).action_verify_result()
                if not any(edition.result_approval_required for edition in editions):
                    self.with_context(workflow_policy_bypass=True).action_approve_result()
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
            editions = self.mapped(lambda match: match._competition_workflow_edition())
            bypass = self.env.context.get("workflow_policy_bypass")
            if not bypass:
                self._check_result_group(
                    "sports_federation_result_control.group_result_validator",
                    "Only result validators can verify submitted results.",
                )
            allow_self = bypass or (
                editions and all(edition.result_self_verification_allowed for edition in editions)
            )
            self._lock_result_transition()
            return self._result_transition(
                "verified",
                {"submitted"},
                values=lambda record: {
                    "result_verified_by_id": self.env.user.id,
                    "result_verified_on": fields.Datetime.now(),
                },
                forbidden_actor_fields=() if allow_self else ("result_submitted_by_id",),
                event_type="verified",
                description="Result verified.",
            )

    def action_approve_result(self):
        """Approve verified results atomically and recompute standings."""
        with self.env.cr.savepoint():
            editions = self.mapped(lambda match: match._competition_workflow_edition())
            bypass = self.env.context.get("workflow_policy_bypass")
            if not bypass:
                self._check_result_group(
                    "sports_federation_result_control.group_result_approver",
                    "Only result approvers can approve verified results.",
                )
            allow_self = bypass or (
                editions and all(edition.result_self_approval_allowed for edition in editions)
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
                forbidden_actor_fields=() if allow_self else (
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


class FederationMatchResultPeriod(models.Model):
    _name = "federation.match.result.period"
    _description = "Match Set or Period Score"
    _order = "sequence,id"

    match_id = fields.Many2one(
        "federation.match", required=True, ondelete="cascade", index=True
    )
    sequence = fields.Integer(string="Set / Period", required=True, default=1)
    home_score = fields.Integer(required=True, default=0)
    away_score = fields.Integer(required=True, default=0)
    note = fields.Char()

    _unique_match_period = models.Constraint(
        "unique(match_id,sequence)",
        "A set or period number can occur only once per match.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        match_ids = [vals.get("match_id") for vals in vals_list if vals.get("match_id")]
        if self.env["federation.match"].browse(match_ids).filtered(
            lambda match: match.result_state == "approved"
        ):
            raise ValidationError(
                _(
                    "Approved set / period scores are immutable. Contest or correct "
                    "the result first."
                )
            )
        return super().create(vals_list)

    @api.constrains("sequence", "home_score", "away_score")
    def _check_period_score(self):
        for period in self:
            if period.sequence < 1:
                raise ValidationError(_("Set / period number must be positive."))
            if period.home_score < 0 or period.away_score < 0:
                raise ValidationError(_("Set / period scores cannot be negative."))

    def _assert_mutable(self):
        if self.mapped("match_id").filtered(
            lambda match: match.result_state == "approved"
        ):
            raise ValidationError(
                _(
                    "Approved set / period scores are immutable. Contest or correct "
                    "the result first."
                )
            )

    def write(self, vals):
        self._assert_mutable()
        return super().write(vals)

    def unlink(self):
        self._assert_mutable()
        return super().unlink()
