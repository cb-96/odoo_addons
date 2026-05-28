from odoo import fields, models


PLANNER_OPERATION_TYPE_SELECTION = [
    ("assign", "Assign"),
    ("move", "Move"),
    ("unassign", "Unassign"),
]

PLANNER_OPERATION_STATE_SELECTION = [
    ("applied", "Applied"),
    ("undone", "Undone"),
    ("superseded", "Superseded"),
]


class FederationCompetitionPlannerOperation(models.Model):
    _name = "federation.competition.planner.operation"
    _description = "Competition Planner Operation"
    _order = "id desc"

    planner_root_round_id = fields.Many2one(
        "federation.tournament.round",
        string="Planner Root Gameday",
        required=True,
        index=True,
        ondelete="cascade",
    )
    match_id = fields.Many2one(
        "federation.match",
        string="Match",
        required=True,
        ondelete="cascade",
    )
    old_slot_id = fields.Many2one(
        "federation.match.slot",
        string="Previous Slot",
        ondelete="set null",
    )
    new_slot_id = fields.Many2one(
        "federation.match.slot",
        string="New Slot",
        ondelete="set null",
    )
    operation_type = fields.Selection(
        PLANNER_OPERATION_TYPE_SELECTION,
        string="Operation Type",
        required=True,
    )
    state = fields.Selection(
        PLANNER_OPERATION_STATE_SELECTION,
        string="State",
        default="applied",
        required=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Actor",
        required=True,
        default=lambda self: self.env.user,
        ondelete="restrict",
    )
    batch_key = fields.Char(
        string="Batch Key",
        index=True,
        copy=False,
    )
    forced = fields.Boolean(
        string="Forced After Warning",
        default=False,
        copy=False,
    )
    override_reason = fields.Text(
        string="Override Reason",
        copy=False,
        help="Manager explanation recorded when a warning-only assignment is forced.",
    )