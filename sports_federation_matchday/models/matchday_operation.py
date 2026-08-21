from odoo import fields, models


class FederationMatchdayIncident(models.Model):
    _name = "federation.matchday.incident"
    _description = "Match-Day Incident"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "occurred_at desc,id desc"
    matchday_id = fields.Many2one(
        "federation.matchday", required=True, ondelete="cascade", index=True
    )
    incident_type = fields.Selection(
        [
            ("delay", "Delay"),
            ("court_unavailable", "Court Unavailable"),
            ("official_missing", "Official Missing"),
            ("schedule_change", "Schedule Change"),
            ("other", "Other"),
        ],
        required=True,
        index=True,
    )
    description = fields.Text(required=True)
    occurred_at = fields.Datetime(
        default=fields.Datetime.now, required=True, index=True
    )
    resolved = fields.Boolean(default=False)
    resolved_at = fields.Datetime()
    resolved_by_id = fields.Many2one("res.users", ondelete="set null")


class FederationMatchdayCourtStatus(models.Model):
    _name = "federation.matchday.court.status"
    _description = "Match-Day Court Status"
    matchday_id = fields.Many2one(
        "federation.matchday", required=True, ondelete="cascade", index=True
    )
    court_id = fields.Many2one(
        "federation.playing.area", required=True, ondelete="restrict", index=True
    )
    state = fields.Selection(
        [
            ("available", "Available"),
            ("delayed", "Delayed"),
            ("unavailable", "Unavailable"),
        ],
        default="available",
        required=True,
        index=True,
    )
    delay_minutes = fields.Integer(default=0)
    note = fields.Char()
    _unique = models.Constraint(
        "unique(matchday_id,court_id)", "A court has one status per match day."
    )
