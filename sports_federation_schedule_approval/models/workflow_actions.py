from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationScheduleApprovalHandoff(models.Model):
    _inherit = "federation.schedule"

    review_count = fields.Integer(compute="_compute_review_handoff")
    current_review_id = fields.Many2one(
        "federation.schedule.review", compute="_compute_review_handoff"
    )

    @api.depends("revision", "state")
    def _compute_review_handoff(self):
        Review = self.env["federation.schedule.review"]
        for schedule in self:
            reviews = Review.search(
                [("schedule_id", "=", schedule.id)], order="id desc"
            )
            schedule.review_count = len(reviews)
            schedule.current_review_id = reviews[:1]

    def action_submit_for_review(self, warning_override_reason=False):
        self.ensure_one()
        result = super().action_submit_for_review(
            warning_override_reason=warning_override_reason
        )
        review = self.env["federation.schedule.approval.commands"].start_review(self.id)
        return review.action_open_review()

    def action_open_current_review(self):
        self.ensure_one()
        review = self.env["federation.schedule.review"].search(
            [("schedule_id", "=", self.id)], order="id desc", limit=1
        )
        if not review:
            raise ValidationError(_("No review exists for this schedule yet."))
        return review.action_open_review()


class FederationScheduleReviewActions(models.Model):
    _inherit = "federation.schedule.review"

    def action_open_review(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Schedule Review"),
            "res_model": "federation.schedule.review",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_schedule(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Working Schedule"),
            "res_model": "federation.schedule",
            "res_id": self.schedule_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_request_changes(self):
        self.ensure_one()
        self.env["federation.schedule.approval.commands"].request_changes(
            self.id, self.review_note
        )
        return self.action_open_review()

    def action_approve_schedule(self):
        self.ensure_one()
        self.env["federation.schedule.approval.commands"].approve(
            self.id, self.review_note
        )
        return self.action_open_review()

    def action_publish_schedule(self):
        self.ensure_one()
        if self.state != "approved":
            raise ValidationError(_("Approve the review before publishing its schedule."))
        publication = self.env["federation.schedule.approval.commands"].publish(
            self.schedule_id.id, reason=self.review_note
        )
        return publication.action_open_publication()


class FederationSchedulePublicationActions(models.Model):
    _inherit = "federation.schedule.publication"

    def action_open_publication(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Published Schedule"),
            "res_model": "federation.schedule.publication",
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_open_schedule(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Source Schedule"),
            "res_model": "federation.schedule",
            "res_id": self.schedule_id.id,
            "view_mode": "form",
            "target": "current",
        }
