from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FederationDisciplinaryAppeal(models.Model):
    _name = "federation.disciplinary.appeal"
    _description = "Disciplinary Appeal"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "submitted_on desc,id desc"

    case_id = fields.Many2one(
        "federation.disciplinary.case", required=True, ondelete="restrict", index=True
    )
    company_id = fields.Many2one(related="case_id.company_id", store=True, index=True)
    appellant_id = fields.Many2one(
        "res.users",
        required=True,
        default=lambda self: self.env.user,
        ondelete="restrict",
    )
    grounds = fields.Text(required=True)
    deadline = fields.Datetime(required=True, index=True)
    evidence_attachment_ids = fields.Many2many(
        "ir.attachment",
        "federation_disciplinary_appeal_attachment_rel",
        "appeal_id",
        "attachment_id",
        string="Evidence",
    )
    reviewer_id = fields.Many2one("res.users", ondelete="restrict", tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("under_review", "Under Review"),
            ("upheld", "Upheld"),
            ("dismissed", "Dismissed"),
            ("withdrawn", "Withdrawn"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    submitted_on = fields.Datetime(readonly=True)
    decided_on = fields.Datetime(readonly=True)
    decision = fields.Text(readonly=True)
    sanction_effect = fields.Selection(
        [
            ("stayed", "Stayed pending appeal"),
            ("confirmed", "Confirmed"),
            ("reduced", "Reduced"),
            ("revoked", "Revoked"),
            ("remitted", "Returned for a new decision"),
        ],
        readonly=True,
    )
    effect_note = fields.Text(readonly=True)

    def _assert_reviewer(self):
        if not self.env.user.has_group(
            "sports_federation_discipline.group_federation_discipline_manager"
        ):
            raise AccessError(_("Only discipline reviewers may decide appeals."))

    @api.constrains("deadline", "submitted_on")
    def _check_deadline(self):
        for appeal in self:
            if appeal.submitted_on and appeal.deadline < appeal.submitted_on:
                raise ValidationError(_("The appeal was submitted after its deadline."))

    def action_submit(self):
        for appeal in self:
            if appeal.state != "draft":
                raise ValidationError(_("Only draft appeals can be submitted."))
            if fields.Datetime.now() > appeal.deadline:
                raise ValidationError(_("The appeal deadline has passed."))
            appeal.write({"state": "submitted", "submitted_on": fields.Datetime.now()})
            appeal.case_id.state = "appealed"
        return True

    def action_start_review(self):
        self._assert_reviewer()
        for appeal in self:
            if appeal.state != "submitted":
                raise ValidationError(_("Only submitted appeals can enter review."))
            appeal.write({"state": "under_review", "reviewer_id": self.env.user.id})
        return True

    def action_decide(
        self, upheld=False, decision=False, effect=False, effect_note=False
    ):
        self._assert_reviewer()
        if not (decision or "").strip() or effect not in dict(
            self._fields["sanction_effect"].selection
        ):
            raise ValidationError(_("Record the decision and its sanction effect."))
        for appeal in self:
            if appeal.state != "under_review":
                raise ValidationError(_("Only an appeal under review can be decided."))
            appeal.write(
                {
                    "state": "upheld" if upheld else "dismissed",
                    "decision": decision.strip(),
                    "sanction_effect": effect,
                    "effect_note": (effect_note or "").strip(),
                    "decided_on": fields.Datetime.now(),
                }
            )
            if not appeal.case_id.appeal_ids.filtered(
                lambda item: item.state in ("submitted", "under_review")
            ):
                appeal.case_id.state = "decided"
        return True

    def action_withdraw(self):
        for appeal in self:
            if appeal.appellant_id != self.env.user or appeal.state not in (
                "draft",
                "submitted",
            ):
                raise AccessError(
                    _("Only the appellant can withdraw an undecided appeal.")
                )
            appeal.state = "withdrawn"
        return True


class FederationDisciplinaryCaseAppeals(models.Model):
    _inherit = "federation.disciplinary.case"

    appeal_ids = fields.One2many(
        "federation.disciplinary.appeal", "case_id", readonly=True
    )
    appeal_count = fields.Integer(compute="_compute_appeal_count")

    @api.depends("appeal_ids")
    def _compute_appeal_count(self):
        for case in self:
            case.appeal_count = len(case.appeal_ids)

    def action_mark_appealed(self):
        for case in self:
            if not case.appeal_ids.filtered(
                lambda item: item.state in ("submitted", "under_review")
            ):
                raise ValidationError(
                    _("Submit an appeal with grounds and a deadline first.")
                )
        return super().action_mark_appealed()

    def action_close(self):
        for case in self:
            if case.appeal_ids.filtered(
                lambda item: item.state in ("submitted", "under_review")
            ):
                raise ValidationError(
                    _(
                        "Decide or withdraw every current appeal before closing "
                        "the case."
                    )
                )
        return super().action_close()


class FederationDisciplinaryAppealDecisionWizard(models.TransientModel):
    _name = "federation.disciplinary.appeal.decision.wizard"
    _description = "Decide Disciplinary Appeal"

    appeal_id = fields.Many2one(
        "federation.disciplinary.appeal", required=True, readonly=True
    )
    upheld = fields.Boolean()
    decision = fields.Text(required=True)
    sanction_effect = fields.Selection(
        [
            ("stayed", "Stayed pending appeal"),
            ("confirmed", "Confirmed"),
            ("reduced", "Reduced"),
            ("revoked", "Revoked"),
            ("remitted", "Returned for a new decision"),
        ],
        required=True,
    )
    effect_note = fields.Text()

    def action_apply(self):
        self.ensure_one()
        self.appeal_id.action_decide(
            upheld=self.upheld,
            decision=self.decision,
            effect=self.sanction_effect,
            effect_note=self.effect_note,
        )
        return self.appeal_id.get_formview_action()


class FederationDisciplinaryAppealDecisionAction(models.Model):
    _inherit = "federation.disciplinary.appeal"

    def action_open_decision(self):
        self.ensure_one()
        self._assert_reviewer()
        wizard = self.env["federation.disciplinary.appeal.decision.wizard"].create(
            {"appeal_id": self.id}
        )
        return wizard.get_formview_action()
