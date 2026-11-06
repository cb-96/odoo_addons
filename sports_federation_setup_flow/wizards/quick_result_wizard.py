from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class QuickResultWizard(models.TransientModel):
    _name = "federation.quick.result.wizard"
    _description = "Quick match result entry"

    match_id = fields.Many2one("federation.match", required=True, readonly=True)
    home_score = fields.Integer(required=True)
    away_score = fields.Integer(required=True)

    score_entry_confirmed = fields.Boolean(string="I checked both scores")
    zero_zero_confirmed = fields.Boolean(string="0-0 is the intended result")
    requires_review = fields.Boolean(compute="_compute_requires_review")

    @api.depends("match_id")
    def _compute_requires_review(self):
        for wizard in self:
            edition = wizard.match_id._competition_workflow_edition() if wizard.match_id else False
            wizard.requires_review = bool(
                edition
                and (edition.result_verification_required or edition.result_approval_required)
            )

    def _save_result(self, submit=False):
        self.ensure_one()
        match = self.match_id
        match.check_access("write")
        match._lock_result_transition()
        if match.state != "done" or match.result_state not in ("draft", "corrected"):
            raise ValidationError(_("Only completed matches awaiting score entry can be edited here. Use the correction workflow for official results."))
        if min(self.home_score, self.away_score) < 0:
            raise ValidationError(_("Scores cannot be negative."))
        match.write({"home_score": self.home_score, "away_score": self.away_score, "score_entry_confirmed": self.score_entry_confirmed, "zero_zero_confirmed": self.zero_zero_confirmed})
        if submit:
            match.action_submit_result()
        return {"type": "ir.actions.act_window_close"}

    def action_save_result(self):
        """Single result command: save the score and hand it to the policy.

        Streamlined competitions make the result official immediately; review
        competitions route it to the independent reviewer.  There is no separate
        draft step for operators to forget.
        """
        self.score_entry_confirmed = True
        return self._save_result(submit=True)

    def action_save(self):
        return self._save_result()

    def action_submit(self):
        return self._save_result(submit=True)
