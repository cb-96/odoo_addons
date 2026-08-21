from odoo import api, fields, models


class FederationSchedule(models.Model):
    _name = "federation.schedule"
    _description = "Competition Working Schedule"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"
    name = fields.Char(required=True)
    edition_id = fields.Many2one(
        "federation.competition.edition", required=True, ondelete="cascade", index=True
    )
    structure_id = fields.Many2one(
        "federation.competition.structure",
        required=True,
        ondelete="restrict",
        index=True,
    )
    matchday_id = fields.Many2one(
        "federation.matchday", required=True, ondelete="restrict", index=True
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("ready_for_review", "Ready for Review"),
            ("changes_requested", "Changes Requested"),
            ("approved", "Approved"),
            ("published", "Published"),
            ("superseded", "Superseded"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    revision = fields.Integer(default=0, required=True, copy=False, index=True)
    assignment_ids = fields.One2many("federation.schedule.assignment", "schedule_id")
    change_ids = fields.One2many(
        "federation.schedule.change", "schedule_id", readonly=True
    )
    _unique_matchday = models.Constraint(
        "unique(matchday_id)", "A match day can have only one active working schedule."
    )


class FederationScheduleAssignment(models.Model):
    _name = "federation.schedule.assignment"
    _description = "Fixture Slot Assignment"
    _order = "slot_id,id"
    schedule_id = fields.Many2one(
        "federation.schedule", required=True, ondelete="cascade", index=True
    )
    fixture_id = fields.Many2one(
        "federation.fixture", required=True, ondelete="restrict", index=True
    )
    slot_id = fields.Many2one(
        "federation.schedule.slot", required=True, ondelete="restrict", index=True
    )
    method = fields.Selection(
        [
            ("manual", "Manual"),
            ("automatic", "Automatic"),
            ("operational", "Operational"),
        ],
        default="manual",
        required=True,
    )
    assigned_by_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        required=True,
        ondelete="restrict",
    )
    _unique_fixture = models.Constraint(
        "unique(schedule_id,fixture_id)",
        "A fixture can be assigned only once in a schedule.",
    )
    _unique_slot = models.Constraint(
        "unique(schedule_id,slot_id)",
        "A slot can contain only one fixture in a schedule.",
    )


class FederationScheduleChange(models.Model):
    _name = "federation.schedule.change"
    _description = "Schedule Change"
    _order = "create_date desc,id desc"
    schedule_id = fields.Many2one(
        "federation.schedule", required=True, ondelete="cascade", index=True
    )
    revision = fields.Integer(required=True, index=True)
    command = fields.Char(required=True, index=True)
    fixture_id = fields.Many2one("federation.fixture", ondelete="set null")
    old_slot_id = fields.Many2one("federation.schedule.slot", ondelete="set null")
    new_slot_id = fields.Many2one("federation.schedule.slot", ondelete="set null")
    actor_id = fields.Many2one(
        "res.users", default=lambda self: self.env.user, ondelete="set null"
    )
    reason = fields.Text()
    idempotency_key = fields.Char(index=True)
