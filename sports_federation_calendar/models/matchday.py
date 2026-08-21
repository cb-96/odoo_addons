from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationMatchday(models.Model):
    _name = "federation.matchday"
    _description = "Physical Competition Match Day"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date,id"
    name = fields.Char(required=True)
    edition_id = fields.Many2one(
        "federation.competition.edition", required=True, ondelete="cascade", index=True
    )
    date = fields.Date(required=True, index=True)
    venue_id = fields.Many2one(
        "federation.venue", required=True, ondelete="restrict", index=True
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("capacity_ready", "Capacity Ready"),
            ("scheduled", "Scheduled"),
            ("open", "Open"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    allocation_ids = fields.One2many("federation.matchday.allocation", "matchday_id")
    slot_ids = fields.One2many("federation.schedule.slot", "matchday_id")
    fixture_count = fields.Integer(compute="_compute_capacity")
    playable_slot_count = fields.Integer(compute="_compute_capacity")
    spare_capacity = fields.Integer(compute="_compute_capacity")

    @api.depends("allocation_ids.fixture_ids", "slot_ids.state")
    def _compute_capacity(self):
        for r in self:
            r.fixture_count = len(r.allocation_ids.mapped("fixture_ids"))
            r.playable_slot_count = len(
                r.slot_ids.filtered(lambda s: s.state == "available")
            )
            r.spare_capacity = r.playable_slot_count - r.fixture_count

    def action_capacity_ready(self):
        for r in self:
            if not r.slot_ids.filtered(lambda s: s.state == "available"):
                raise ValidationError("Generate playable slots first.")
            if not r.allocation_ids:
                raise ValidationError("Allocate fixtures or rounds first.")
            r.state = "capacity_ready"
        return True


class FederationMatchdayAllocation(models.Model):
    _name = "federation.matchday.allocation"
    _description = "Match-Day Fixture Allocation"
    matchday_id = fields.Many2one(
        "federation.matchday", required=True, ondelete="cascade", index=True
    )
    structure_id = fields.Many2one(
        "federation.competition.structure",
        required=True,
        ondelete="restrict",
        index=True,
    )
    stage_id = fields.Many2one(
        "federation.structure.stage", ondelete="restrict", index=True
    )
    round_number = fields.Integer(index=True)
    fixture_ids = fields.Many2many("federation.fixture", compute="_compute_fixtures")

    @api.depends("structure_id", "stage_id", "round_number")
    def _compute_fixtures(self):
        Fixture = self.env["federation.fixture"]
        for r in self:
            domain = (
                [("structure_id", "=", r.structure_id.id)]
                if r.structure_id
                else [("id", "=", False)]
            )
            if r.stage_id:
                domain.append(("stage_id", "=", r.stage_id.id))
            if r.round_number:
                domain.append(("round_number", "=", r.round_number))
            r.fixture_ids = Fixture.search(domain)


class FederationScheduleSlot(models.Model):
    _name = "federation.schedule.slot"
    _description = "Physical Schedule Slot"
    _order = "start_datetime,court_id,id"
    matchday_id = fields.Many2one(
        "federation.matchday", required=True, ondelete="cascade", index=True
    )
    court_id = fields.Many2one(
        "federation.playing.area", required=True, ondelete="restrict", index=True
    )
    start_datetime = fields.Datetime(required=True, index=True)
    end_datetime = fields.Datetime(required=True, index=True)
    state = fields.Selection(
        [("available", "Available"), ("break", "Break"), ("blocked", "Blocked")],
        default="available",
        required=True,
        index=True,
    )
    note = fields.Char()

    @api.constrains("start_datetime", "end_datetime")
    def _check_window(self):
        for r in self:
            if r.end_datetime <= r.start_datetime:
                raise ValidationError("A slot must end after it starts.")
