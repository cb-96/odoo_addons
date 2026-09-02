from odoo import fields, models


class FederationScheduleReview(models.Model):
    _name = "federation.schedule.review"
    _description = "Independent Schedule Review"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    schedule_id = fields.Many2one(
        "federation.schedule", required=True, ondelete="cascade", index=True
    )
    edition_id = fields.Many2one(
        related="schedule_id.edition_id", store=True, index=True
    )
    submitted_revision = fields.Integer(required=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("withdrawn", "Withdrawn"),
            ("changes_requested", "Changes Requested"),
            ("approved", "Approved"),
        ],
        default="pending",
        required=True,
        tracking=True,
        index=True,
    )
    reviewer_id = fields.Many2one("res.users", ondelete="set null")
    review_note = fields.Text()
    assignment_snapshot = fields.Json(required=True)


class FederationSchedulePublication(models.Model):
    _name = "federation.schedule.publication"
    _description = "Immutable Schedule Publication"
    _order = "version desc,id desc"
    schedule_id = fields.Many2one(
        "federation.schedule", required=True, ondelete="restrict", index=True
    )
    edition_id = fields.Many2one(
        related="schedule_id.edition_id", store=True, index=True
    )
    matchday_id = fields.Many2one(
        related="schedule_id.matchday_id", store=True, index=True
    )
    version = fields.Integer(required=True)
    state = fields.Selection(
        [("live", "Live"), ("superseded", "Superseded")],
        default="live",
        required=True,
        index=True,
    )
    published_by_id = fields.Many2one(
        "res.users", default=lambda s: s.env.user, required=True, ondelete="restrict"
    )
    published_at = fields.Datetime(default=fields.Datetime.now, required=True)
    reason = fields.Text()
    assignment_snapshot = fields.Json(required=True)
    _unique_version = models.Constraint(
        "unique(matchday_id,version)",
        "Publication versions must be unique per match day.",
    )
