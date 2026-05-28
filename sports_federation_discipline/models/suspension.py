from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationSuspension(models.Model):
    _name = "federation.suspension"
    _description = "Suspension"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"

    name = fields.Char(required=True)
    case_id = fields.Many2one(
        "federation.disciplinary.case",
        string="Case",
        required=True,
        ondelete="cascade",
        index=True,
    )
    player_id = fields.Many2one(
        "federation.player",
        string="Player",
        required=True,
        ondelete="restrict",
        index=True,
    )
    date_start = fields.Date(string="Start Date", required=True)
    date_end = fields.Date(string="End Date", required=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
    )
    notes = fields.Text(string="Notes")

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        """Validate dates."""
        for record in self:
            if record.date_end and record.date_start:
                if record.date_end < record.date_start:
                    raise ValidationError("End date must be on or after start date.")

    def action_activate(self):
        """Activate the suspension and mark the affected player as suspended."""
        records_to_activate = self.filtered(lambda record: record.state != "active")
        if not records_to_activate:
            return

        records_to_activate.write({"state": "active"})

        for record in records_to_activate:
            record.player_id.action_suspend()

        dispatcher = self.env.get("federation.notification.dispatcher")
        if dispatcher is not None:
            for record in records_to_activate:
                dispatcher.send_suspension_issued(record)

    def action_cancel(self):
        """Cancel the suspension and restore the player's state if no other active suspensions remain."""
        for record in self:
            record.state = "cancelled"
            record._maybe_restore_player_state()

    def action_expire(self):
        """Mark the suspension as expired and restore the player's state if eligible."""
        records_to_expire = self.filtered(lambda record: record.state == "active")
        records_to_expire.write({"state": "expired"})
        for record in records_to_expire:
            record._maybe_restore_player_state()

    def _maybe_restore_player_state(self):
        """Restore the player to active if they have no remaining active suspensions."""
        self.ensure_one()
        player = self.player_id
        active_suspensions = self.env["federation.suspension"].search(
            [
                ("player_id", "=", player.id),
                ("state", "=", "active"),
                ("id", "!=", self.id),
            ],
            limit=1,
        )
        if not active_suspensions:
            player.action_activate()
