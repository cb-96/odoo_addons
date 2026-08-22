from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
    fairness_same_club_weight = fields.Float(
        string="Same-club overlap weight", default=40.0, required=True,
        help="Penalty when teams belonging to the same club play simultaneously.",
    )
    fairness_rest_weight = fields.Float(
        string="Rest shortfall weight", default=3.0, required=True,
        help="Penalty per missing minute below the preferred break.",
    )
    fairness_consecutive_weight = fields.Float(
        string="Consecutive-games weight", default=60.0, required=True,
        help="Penalty for each game above the configured consecutive-game limit.",
    )
    fairness_time_balance_weight = fields.Float(
        string="Time-balance weight", default=1.0, required=True,
        help="Penalty for uneven early/late play distribution between teams.",
    )
    fairness_court_balance_weight = fields.Float(
        string="Court-repeat weight", default=2.0, required=True,
        help="Penalty for repeatedly scheduling a team on the same court.",
    )
    preferred_rest_minutes = fields.Integer(default=40, required=True)
    max_consecutive_games = fields.Integer(default=2, required=True)
    fairness_last_score = fields.Float(readonly=True, copy=False)
    fairness_last_report = fields.Json(readonly=True, copy=False)

    @api.constrains(
        "fairness_same_club_weight", "fairness_rest_weight",
        "fairness_consecutive_weight", "fairness_time_balance_weight",
        "fairness_court_balance_weight", "preferred_rest_minutes",
        "max_consecutive_games",
    )
    def _check_fairness_configuration(self):
        for rec in self:
            weights = (
                rec.fairness_same_club_weight, rec.fairness_rest_weight,
                rec.fairness_consecutive_weight, rec.fairness_time_balance_weight,
                rec.fairness_court_balance_weight,
            )
            if any(weight < 0 for weight in weights):
                raise ValidationError("Fairness weights cannot be negative.")
            if rec.preferred_rest_minutes < 0:
                raise ValidationError("Preferred rest cannot be negative.")
            if rec.max_consecutive_games < 1:
                raise ValidationError("Maximum consecutive games must be at least one.")

    def action_open_auto_schedule(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Auto-schedule matches",
            "res_model": "federation.schedule.auto.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_schedule_id": self.id},
        }

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
