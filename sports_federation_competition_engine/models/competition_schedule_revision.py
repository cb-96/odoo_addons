from odoo import fields, models


SCHEDULE_REVISION_STATE_SELECTION = [
    ("draft", "Draft"),
    ("live", "Current Live"),
    ("superseded", "Superseded"),
]


class FederationCompetitionScheduleRevision(models.Model):
    _name = "federation.competition.schedule.revision"
    _description = "Competition Schedule Revision"
    _order = "planner_root_round_id, revision_number desc, id desc"

    name = fields.Char(
        string="Revision Name",
        required=True,
        copy=False,
    )
    planner_root_round_id = fields.Many2one(
        "federation.tournament.round",
        string="Planner Root Gameday",
        required=True,
        index=True,
        ondelete="cascade",
    )
    edition_id = fields.Many2one(
        "federation.competition.edition",
        string="Competition",
        required=True,
        index=True,
        ondelete="cascade",
    )
    revision_number = fields.Integer(
        string="Revision Number",
        required=True,
        copy=False,
    )
    state = fields.Selection(
        SCHEDULE_REVISION_STATE_SELECTION,
        string="State",
        default="draft",
        required=True,
        copy=False,
    )
    based_on_revision_id = fields.Many2one(
        "federation.competition.schedule.revision",
        string="Based On Revision",
        ondelete="set null",
        copy=False,
    )
    published_on = fields.Datetime(
        string="Published On",
        copy=False,
    )
    published_by_id = fields.Many2one(
        "res.users",
        string="Published By",
        ondelete="set null",
        copy=False,
    )
    override_reason = fields.Text(
        string="Override Reason",
        copy=False,
        help="Required manager explanation when a draft replaces a live schedule or publishes with warnings.",
    )
    snapshot_payload = fields.Text(
        string="Snapshot Payload",
        copy=False,
        help="Serialized slot and match snapshot captured for this revision.",
    )
    slot_count = fields.Integer(
        string="Slot Count",
        default=0,
        copy=False,
    )
    assigned_match_count = fields.Integer(
        string="Assigned Match Count",
        default=0,
        copy=False,
    )
    warning_count = fields.Integer(
        string="Warning Count",
        default=0,
        copy=False,
    )