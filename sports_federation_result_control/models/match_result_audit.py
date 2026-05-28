from odoo import api, fields, models


class FederationMatchResultAudit(models.Model):
    _name = "federation.match.result.audit"
    _description = "Match Result Audit"
    _order = "created_on desc, id desc"

    event_type = fields.Selection(
        [
            ("submitted", "Submitted"),
            ("verified", "Verified"),
            ("approved", "Approved"),
            ("contested", "Contested"),
            ("corrected", "Corrected"),
            ("reset", "Reset To Draft"),
        ],
        string="Event Type",
        required=True,
        index=True,
    )
    match_id = fields.Many2one(
        "federation.match",
        string="Match",
        required=True,
        ondelete="cascade",
        index=True,
    )
    from_state = fields.Char(string="From State")
    to_state = fields.Char(string="To State")
    reason = fields.Text(string="Reason")
    description = fields.Text(string="Description", required=True)
    author_id = fields.Many2one(
        "res.users",
        string="Author",
        required=True,
        readonly=True,
    )
    created_on = fields.Datetime(
        string="Created On",
        default=fields.Datetime.now,
        required=True,
        readonly=True,
    )

    @api.model
    def create_event(
        self,
        match,
        event_type,
        description,
        from_state,
        to_state,
        reason=False,
        author=False,
    ):
        """Handle create event."""
        return self.sudo().create(
            {
                "match_id": match.id,
                "event_type": event_type,
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
                "description": description,
                "author_id": author.id if author else self.env.user.id,
            }
        )
