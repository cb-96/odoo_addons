from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationMatchOperationalState(models.Model):
    _inherit = "federation.match"

    operational_slot_id = fields.Many2one(
        "federation.schedule.slot",
        readonly=True,
        copy=False,
        ondelete="restrict",
        index=True,
        help="Current operational slot. The immutable published slot remains unchanged.",
    )
    operational_status = fields.Selection(
        [
            ("as_published", "As Published"),
            ("moved", "Moved"),
            ("delayed", "Delayed"),
            ("postponed", "Postponed"),
            ("cancelled", "Cancelled"),
        ],
        default="as_published",
        readonly=True,
        copy=False,
        index=True,
    )
    operational_deviation_ids = fields.One2many(
        "federation.matchday.deviation", "match_id", readonly=True
    )


class FederationMatchdayDeviation(models.Model):
    _name = "federation.matchday.deviation"
    _description = "Immutable Match-Day Schedule Deviation"
    _order = "occurred_at desc,id desc"

    matchday_id = fields.Many2one(
        "federation.matchday",
        required=True,
        readonly=True,
        ondelete="restrict",
        index=True,
    )
    session_id = fields.Many2one(
        "federation.matchday.session",
        required=True,
        readonly=True,
        ondelete="restrict",
        index=True,
    )
    publication_id = fields.Many2one(
        "federation.schedule.publication",
        required=True,
        readonly=True,
        ondelete="restrict",
        index=True,
    )
    match_id = fields.Many2one(
        "federation.match",
        required=True,
        readonly=True,
        ondelete="restrict",
        index=True,
    )
    deviation_type = fields.Selection(
        [
            ("move", "Move"),
            ("delay", "Delay"),
            ("postpone", "Postpone"),
            ("cancel", "Cancel"),
        ],
        required=True,
        readonly=True,
        index=True,
    )
    old_slot_id = fields.Many2one(
        "federation.schedule.slot", readonly=True, ondelete="restrict"
    )
    new_slot_id = fields.Many2one(
        "federation.schedule.slot", readonly=True, ondelete="restrict"
    )
    delay_minutes = fields.Integer(readonly=True)
    reason = fields.Text(required=True, readonly=True)
    occurred_at = fields.Datetime(
        default=fields.Datetime.now, required=True, readonly=True, index=True
    )
    actor_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        required=True,
        readonly=True,
        ondelete="restrict",
    )

    def write(self, vals):
        raise ValidationError(_("Operational deviation evidence is immutable."))

    def unlink(self):
        raise ValidationError(
            _("Operational deviation evidence is retained for audit.")
        )


class FederationMatchdayOperatorActions(models.Model):
    _inherit = "federation.matchday"

    readiness_state = fields.Selection(
        [
            ("blocked", "Blocked"),
            ("ready", "Ready"),
            ("open", "Open"),
            ("closed", "Closed"),
        ],
        compute="_compute_operational_readiness",
    )
    readiness_message = fields.Text(compute="_compute_operational_readiness")
    published_match_count = fields.Integer(compute="_compute_operational_readiness")
    unfinished_match_count = fields.Integer(compute="_compute_operational_readiness")
    unresolved_incident_count = fields.Integer(compute="_compute_operational_readiness")
    unavailable_court_count = fields.Integer(compute="_compute_operational_readiness")
    deviation_count = fields.Integer(compute="_compute_operational_readiness")
    incident_ids = fields.One2many(
        "federation.matchday.incident", "matchday_id", readonly=True
    )
    court_status_ids = fields.One2many(
        "federation.matchday.court.status", "matchday_id", readonly=True
    )
    deviation_ids = fields.One2many(
        "federation.matchday.deviation", "matchday_id", readonly=True
    )
    published_match_ids = fields.Many2many(
        "federation.match", compute="_compute_published_matches"
    )

    def _compute_published_matches(self):
        Match = self.env["federation.match"]
        for day in self:
            publication = day.current_publication_id
            day.published_match_ids = (
                Match.search([("schedule_publication_id", "=", publication.id)])
                if publication
                else Match
            )

    def _compute_operational_readiness(self):
        Match = self.env["federation.match"]
        Incident = self.env["federation.matchday.incident"]
        Status = self.env["federation.matchday.court.status"]
        Deviation = self.env["federation.matchday.deviation"]
        for day in self:
            publication = day.current_publication_id
            matches = (
                Match.search([("schedule_publication_id", "=", publication.id)])
                if publication
                else Match
            )
            day.published_match_count = len(matches)
            day.unfinished_match_count = len(
                matches.filtered(lambda m: m.state not in ("done", "cancelled"))
            )
            day.unresolved_incident_count = Incident.search_count(
                [("matchday_id", "=", day.id), ("resolved", "=", False)]
            )
            day.unavailable_court_count = Status.search_count(
                [("matchday_id", "=", day.id), ("state", "=", "unavailable")]
            )
            day.deviation_count = Deviation.search_count([("matchday_id", "=", day.id)])
            if day.state == "open":
                day.readiness_state = "open"
                day.readiness_message = _(
                    "Live operations are active against publication %(version)s.",
                    version=publication.version if publication else "?",
                )
            elif day.state == "closed":
                day.readiness_state = "closed"
                day.readiness_message = _(
                    "Match-day operations are closed and retained as audit evidence."
                )
            elif not publication or publication.state != "live":
                day.readiness_state = "blocked"
                day.readiness_message = _(
                    "Publish an approved schedule before opening match-day operations."
                )
            elif not matches:
                day.readiness_state = "blocked"
                day.readiness_message = _(
                    "The live publication contains no operational matches."
                )
            else:
                day.readiness_state = "ready"
                day.readiness_message = _(
                    "The live publication passed readiness checks and can be opened."
                )

    def action_open_matchday_operations(self):
        self.ensure_one()
        self.env["federation.matchday.commands"].open_matchday(self.id)
        return {"type": "ir.actions.client", "tag": "reload"}

    def action_close_matchday_operations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Close Match Day"),
            "res_model": "federation.matchday.close.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_matchday_id": self.id},
        }

    def action_open_deviation_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Record Operational Schedule Change"),
            "res_model": "federation.matchday.deviation.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_matchday_id": self.id},
        }

    def action_open_court_status_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Update Court Status"),
            "res_model": "federation.matchday.court.status.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_matchday_id": self.id},
        }

    def action_open_incident_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Report Match-Day Incident"),
            "res_model": "federation.matchday.incident.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_matchday_id": self.id},
        }


class FederationMatchdayIncidentActions(models.Model):
    _inherit = "federation.matchday.incident"

    def action_resolve(self):
        self.ensure_one()
        self.env["federation.matchday.commands"].resolve_incident(self.id)
        return {"type": "ir.actions.client", "tag": "reload"}
