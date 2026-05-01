from odoo import api, fields, models


class FederationParticipationAudit(models.Model):
    _name = "federation.participation.audit"
    _description = "Participation Audit Event"
    _order = "event_on desc, id desc"

    event_type = fields.Selection(
        [
            ("roster_created", "Roster Created"),
            ("roster_updated", "Roster Updated"),
            ("roster_activated", "Roster Activated"),
            ("roster_closed", "Roster Closed"),
            ("roster_line_added", "Roster Line Added"),
            ("roster_line_updated", "Roster Line Updated"),
            ("roster_line_removed", "Roster Line Removed"),
            ("match_sheet_created", "Match Sheet Created"),
            ("match_sheet_submitted", "Match Sheet Submitted"),
            ("match_sheet_reset", "Match Sheet Reset to Draft"),
            ("match_sheet_approved", "Match Sheet Approved"),
            ("match_sheet_locked", "Match Sheet Locked"),
            ("sheet_line_added", "Match Sheet Line Added"),
            ("sheet_line_updated", "Match Sheet Line Updated"),
            ("sheet_line_removed", "Match Sheet Line Removed"),
            ("substitution_recorded", "Substitution Recorded"),
        ],
        string="Event Type",
        required=True,
        index=True,
    )
    description = fields.Text(string="Description", required=True)
    team_id = fields.Many2one(
        "federation.team",
        string="Team",
        required=True,
        ondelete="restrict",
        index=True,
    )
    roster_id = fields.Many2one(
        "federation.team.roster",
        string="Roster",
        ondelete="cascade",
        index=True,
    )
    match_sheet_id = fields.Many2one(
        "federation.match.sheet",
        string="Match Sheet",
        ondelete="set null",
        index=True,
    )
    match_id = fields.Many2one(
        "federation.match",
        string="Match",
        ondelete="cascade",
        index=True,
    )
    player_id = fields.Many2one(
        "federation.player",
        string="Player",
        ondelete="set null",
        index=True,
    )
    author_id = fields.Many2one(
        "res.users",
        string="Author",
        default=lambda self: self.env.user,
        required=True,
        readonly=True,
    )
    event_on = fields.Datetime(
        string="Event On",
        default=fields.Datetime.now,
        required=True,
        readonly=True,
    )

    @api.model
    def create_event(
        self,
        event_type,
        description,
        team,
        roster=False,
        match_sheet=False,
        player=False,
        match=False,
        author=False,
    ):
        """Handle create event."""
        match = match or (match_sheet.match_id if match_sheet else False)
        return self.create(
            {
                "event_type": event_type,
                "description": description,
                "team_id": team.id,
                "roster_id": roster.id if roster else False,
                "match_sheet_id": match_sheet.id if match_sheet else False,
                "match_id": match.id if match else False,
                "player_id": player.id if player else False,
                "author_id": author.id if author else self.env.user.id,
            }
        )
