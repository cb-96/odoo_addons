from odoo import fields, models

WORKSPACE_SECTION_SELECTION = [
    ("overview", "Overview"),
    ("teams", "Teams"),
    ("rounds", "Rounds"),
    ("gamedays", "Gamedays"),
    ("planner", "Planner"),
    ("publish", "Publish"),
]


class FederationCompetitionWorkspacePresence(models.Model):
    _name = "federation.competition.workspace.presence"
    _description = "Competition Workspace Presence"
    _order = "last_seen desc, id desc"

    user_id = fields.Many2one(
        "res.users",
        string="User",
        required=True,
        default=lambda self: self.env.user,
        ondelete="cascade",
    )
    competition_id = fields.Many2one(
        "federation.competition.edition",
        string="Competition",
        required=True,
        index=True,
        ondelete="cascade",
    )
    division_id = fields.Many2one(
        "federation.tournament",
        string="Division",
        ondelete="set null",
    )
    planner_root_round_id = fields.Many2one(
        "federation.tournament.round",
        string="Planner Root Gameday",
        index=True,
        ondelete="set null",
    )
    active_section = fields.Selection(
        WORKSPACE_SECTION_SELECTION,
        string="Active Section",
        default="overview",
        required=True,
    )
    last_seen = fields.Datetime(
        string="Last Seen",
        required=True,
        default=lambda self: fields.Datetime.now(),
        index=True,
    )
