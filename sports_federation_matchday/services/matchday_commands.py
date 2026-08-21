from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationMatchdayCommands(models.AbstractModel):
    _name = "federation.matchday.commands"
    _description = "Match-Day Operations Commands"

    def _resolve(self, matchday_id):
        m = self.env["federation.matchday"].browse(int(matchday_id)).exists()
        if not m:
            raise ValidationError(_("The match day no longer exists."))
        self.env["federation.competition.role.assignment"].assert_role(
            m.edition_id, "matchday_manager", "competition_director"
        )
        return m

    @api.model
    def open_matchday(self, matchday_id):
        m = self._resolve(matchday_id)
        if m.state != "scheduled":
            raise ValidationError(
                _("Only a published scheduled match day can be opened.")
            )
        m.state = "open"
        self.env["federation.competition.event"].emit(m, "matchday_opened", {})
        return True

    @api.model
    def report_incident(self, matchday_id, incident_type, description):
        m = self._resolve(matchday_id)
        return self.env["federation.matchday.incident"].create(
            {
                "matchday_id": m.id,
                "incident_type": incident_type,
                "description": description,
            }
        )

    @api.model
    def close_matchday(self, matchday_id):
        m = self._resolve(matchday_id)
        if m.state != "open":
            raise ValidationError(_("Open the match day before closing it."))
        m.state = "closed"
        self.env["federation.competition.event"].emit(m, "matchday_closed", {})
        return True
