from html import escape

from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationMatchdayCloseWizard(models.TransientModel):
    _name = "federation.matchday.close.wizard"
    _description = "Close Match Day"

    matchday_id = fields.Many2one("federation.matchday", required=True, readonly=True)
    force = fields.Boolean(string="Force close with blockers")
    close_note = fields.Text(string="Close reason")

    def action_close(self):
        self.ensure_one()
        self.env["federation.matchday.commands"].close_matchday(
            self.matchday_id.id, close_note=self.close_note, force=self.force
        )
        return {"type": "ir.actions.act_window_close"}


class FederationMatchdayIncidentWizard(models.TransientModel):
    _name = "federation.matchday.incident.wizard"
    _description = "Report Match-Day Incident"

    matchday_id = fields.Many2one("federation.matchday", required=True, readonly=True)
    incident_type = fields.Selection(
        [
            ("delay", "Delay"),
            ("court_unavailable", "Court Unavailable"),
            ("official_missing", "Official Missing"),
            ("schedule_change", "Schedule Change"),
            ("other", "Other"),
        ],
        required=True,
    )
    description = fields.Text(required=True)

    def action_report(self):
        self.ensure_one()
        self.env["federation.matchday.commands"].report_incident(
            self.matchday_id.id, self.incident_type, self.description
        )
        return {"type": "ir.actions.act_window_close"}


class FederationMatchdayDeviationWizard(models.TransientModel):
    _name = "federation.matchday.deviation.wizard"
    _description = "Record Operational Schedule Deviation"

    matchday_id = fields.Many2one("federation.matchday", required=True, readonly=True)
    match_id = fields.Many2one(
        "federation.match",
        required=True,
        domain="[('schedule_publication_id','=',matchday_id.current_publication_id)]",
    )
    deviation_type = fields.Selection(
        [
            ("move", "Move"),
            ("delay", "Delay"),
            ("postpone", "Postpone"),
            ("cancel", "Cancel"),
        ],
        required=True,
    )
    new_slot_id = fields.Many2one(
        "federation.schedule.slot",
        domain="[('matchday_id','=',matchday_id),('state','=','available')]",
    )
    delay_minutes = fields.Integer(default=0)
    reason = fields.Text(required=True)
    impact_preview = fields.Json(readonly=True)
    impact_signature = fields.Char(readonly=True)
    impact_html = fields.Html(readonly=True, sanitize=True)

    def _impact(self):
        self.ensure_one()
        return self.env["federation.matchday.commands"].preview_schedule_deviation(
            self.matchday_id.id,
            self.match_id.id,
            self.deviation_type,
            new_slot_id=self.new_slot_id.id if self.new_slot_id else False,
            delay_minutes=self.delay_minutes,
        )

    def action_preview(self):
        self.ensure_one()
        impact = self._impact()
        labels = [
            (_("Teams affected"), len(impact["team_ids"])),
            (_("Officials requiring reconfirmation"), len(impact["official_ids"])),
            (_("Club duties requiring review"), len(impact["duty_ids"])),
            (_("Line-ups requiring revalidation"), len(impact["roster_ids"])),
            (_("Existing communications"), impact["communication_count"]),
            (
                _("Public calendar changes"),
                _("Yes") if impact["public_calendar_changes"] else _("No"),
            ),
        ]
        html = "<ul>%s</ul>" % "".join(
            "<li><strong>%s:</strong> %s</li>"
            % (escape(str(label)), escape(str(value)))
            for label, value in labels
        )
        self.write(
            {
                "impact_preview": impact,
                "impact_signature": impact["signature"],
                "impact_html": html,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_apply(self):
        self.ensure_one()
        if self.deviation_type == "move" and not self.new_slot_id:
            raise ValidationError(_("Select the new slot for a moved match."))
        if self.deviation_type == "delay" and self.delay_minutes <= 0:
            raise ValidationError(_("Enter a positive delay in minutes."))
        if (
            not self.impact_signature
            or self._impact()["signature"] != self.impact_signature
        ):
            raise ValidationError(
                _("Review the current change impact before applying.")
            )
        self.env["federation.matchday.commands"].record_schedule_deviation(
            self.matchday_id.id,
            self.match_id.id,
            self.deviation_type,
            reason=self.reason,
            new_slot_id=self.new_slot_id.id if self.new_slot_id else False,
            delay_minutes=self.delay_minutes,
            expected_impact_signature=self.impact_signature,
        )
        return {"type": "ir.actions.act_window_close"}


class FederationMatchdayCourtStatusWizard(models.TransientModel):
    _name = "federation.matchday.court.status.wizard"
    _description = "Update Match-Day Court Status"

    matchday_id = fields.Many2one("federation.matchday", required=True, readonly=True)
    court_id = fields.Many2one(
        "federation.playing.area",
        required=True,
        domain="[('id','in',matchday_id.slot_ids.court_id)]",
    )
    state = fields.Selection(
        [
            ("available", "Available"),
            ("delayed", "Delayed"),
            ("unavailable", "Unavailable"),
        ],
        required=True,
        default="available",
    )
    delay_minutes = fields.Integer(default=0)
    note = fields.Char()

    def action_apply(self):
        self.ensure_one()
        self.env["federation.matchday.commands"].set_court_status(
            self.matchday_id.id,
            self.court_id.id,
            self.state,
            delay_minutes=self.delay_minutes,
            note=self.note,
        )
        return {"type": "ir.actions.act_window_close"}
