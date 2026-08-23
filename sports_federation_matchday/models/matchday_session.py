from odoo import fields, models
from odoo.exceptions import ValidationError


class FederationMatchdaySession(models.Model):
    _name = "federation.matchday.session"
    _description = "Match-Day Execution Session"
    _order = "opened_at desc,id desc"

    matchday_id = fields.Many2one(
        "federation.matchday", required=True, ondelete="restrict", index=True
    )
    publication_id = fields.Many2one(
        "federation.schedule.publication",
        required=True,
        ondelete="restrict",
        index=True,
    )
    publication_digest = fields.Char(required=True, readonly=True)
    state = fields.Selection(
        [("open", "Open"), ("closed", "Closed")],
        default="open",
        required=True,
        index=True,
    )
    opened_at = fields.Datetime(
        default=fields.Datetime.now, required=True, readonly=True
    )
    opened_by_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        required=True,
        readonly=True,
        ondelete="restrict",
    )
    closed_at = fields.Datetime(readonly=True)
    closed_by_id = fields.Many2one("res.users", readonly=True, ondelete="restrict")
    close_note = fields.Text(readonly=True)

    def unlink(self):
        raise ValidationError("Match-day sessions are retained as audit evidence.")


class FederationMatchdaySessionLink(models.Model):
    _inherit = "federation.matchday"

    session_ids = fields.One2many(
        "federation.matchday.session", "matchday_id", readonly=True
    )
    active_session_id = fields.Many2one(
        "federation.matchday.session", compute="_compute_active_session"
    )

    def _compute_active_session(self):
        Session = self.env["federation.matchday.session"]
        for record in self:
            record.active_session_id = Session.search(
                [("matchday_id", "=", record.id), ("state", "=", "open")], limit=1
            )
