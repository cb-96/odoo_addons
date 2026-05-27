from odoo import models


class _PortalLabelMixin(models.AbstractModel):
    _name = "federation.portal.label.mixin"
    _description = "Portal label helper mixin"

    def _portal_label_from_selection(self, field_name):
        self.ensure_one()
        selection = dict(self._fields[field_name].selection)
        value = self[field_name]
        return selection.get(value, value or "")


class FederationTournament(models.Model):
    _inherit = ["federation.tournament", "federation.portal.label.mixin"]

    _PORTAL_TOURNAMENT_STATE_LABELS = {
        "draft": "Planning",
        "open": "Open for entries",
        "in_progress": "Live",
        "closed": "Completed",
        "cancelled": "Cancelled",
    }

    def get_portal_state_label(self):
        self.ensure_one()
        return self._PORTAL_TOURNAMENT_STATE_LABELS.get(
            self.state, self._portal_label_from_selection("state")
        )


class FederationTournamentRegistration(models.Model):
    _inherit = [
        "federation.tournament.registration",
        "federation.portal.label.mixin",
    ]

    _PORTAL_TOURNAMENT_REGISTRATION_STATE_LABELS = {
        "draft": "Draft",
        "submitted": "Awaiting federation review",
        "confirmed": "Confirmed",
        "rejected": "Not accepted",
        "cancelled": "Cancelled",
    }

    def get_portal_state_label(self):
        self.ensure_one()
        return self._PORTAL_TOURNAMENT_REGISTRATION_STATE_LABELS.get(
            self.state, self._portal_label_from_selection("state")
        )


class FederationSeasonRegistration(models.Model):
    _inherit = ["federation.season.registration", "federation.portal.label.mixin"]

    _PORTAL_SEASON_REGISTRATION_STATE_LABELS = {
        "draft": "Draft",
        "submitted": "Awaiting federation review",
        "confirmed": "Confirmed",
        "rejected": "Not accepted",
        "cancelled": "Cancelled",
    }

    def get_portal_state_label(self):
        self.ensure_one()
        return self._PORTAL_SEASON_REGISTRATION_STATE_LABELS.get(
            self.state, self._portal_label_from_selection("state")
        )


class FederationTournamentParticipant(models.Model):
    _inherit = [
        "federation.tournament.participant",
        "federation.portal.label.mixin",
    ]

    _PORTAL_PARTICIPANT_STATE_LABELS = {
        "registered": "Entry received",
        "confirmed": "Confirmed",
        "withdrawn": "Withdrawn",
    }

    def get_portal_state_label(self):
        self.ensure_one()
        return self._PORTAL_PARTICIPANT_STATE_LABELS.get(
            self.state, self._portal_label_from_selection("state")
        )


class FederationMatch(models.Model):
    _inherit = ["federation.match", "federation.portal.label.mixin"]

    _PORTAL_MATCH_STATE_LABELS = {
        "draft": "Not scheduled",
        "scheduled": "Scheduled",
        "in_progress": "Live",
        "done": "Finished",
        "cancelled": "Cancelled",
    }

    _PORTAL_RESULT_STATE_LABELS = {
        "draft": "Not sent",
        "submitted": "Sent for check",
        "verified": "Checked",
        "approved": "Official",
        "contested": "Under review",
        "corrected": "Corrected - resend",
    }

    def get_portal_state_label(self):
        self.ensure_one()
        return self._PORTAL_MATCH_STATE_LABELS.get(
            self.state, self._portal_label_from_selection("state")
        )

    def get_portal_result_state_label(self):
        self.ensure_one()
        return self._PORTAL_RESULT_STATE_LABELS.get(
            self.result_state, self._portal_label_from_selection("result_state")
        )


class FederationMatchSheet(models.Model):
    _inherit = ["federation.match.sheet", "federation.portal.label.mixin"]

    _PORTAL_MATCH_SHEET_STATE_LABELS = {
        "draft": "Draft",
        "submitted": "Submitted",
        "approved": "Approved",
        "rejected": "Needs update",
    }

    def get_portal_state_label(self):
        self.ensure_one()
        return self._PORTAL_MATCH_SHEET_STATE_LABELS.get(
            self.state, self._portal_label_from_selection("state")
        )


class FederationTeamRoster(models.Model):
    _inherit = ["federation.team.roster", "federation.portal.label.mixin"]

    _PORTAL_ROSTER_STATUS_LABELS = {
        "draft": "Draft",
        "active": "Active",
        "closed": "Closed",
    }

    def get_portal_status_label(self):
        self.ensure_one()
        return self._PORTAL_ROSTER_STATUS_LABELS.get(
            self.status, self._portal_label_from_selection("status")
        )


class FederationMatchReferee(models.Model):
    _inherit = ["federation.match.referee", "federation.portal.label.mixin"]

    _PORTAL_ASSIGNMENT_STATE_LABELS = {
        "draft": "Pending response",
        "confirmed": "Confirmed",
        "done": "Completed",
        "declined": "Declined",
        "cancelled": "Cancelled",
    }

    def get_portal_state_label(self):
        self.ensure_one()
        return self._PORTAL_ASSIGNMENT_STATE_LABELS.get(
            self.state, self._portal_label_from_selection("state")
        )


class FederationRefereeDuty(models.Model):
    _inherit = [
        "federation.match.club.referee.duty",
        "federation.portal.label.mixin",
    ]

    _PORTAL_DUTY_STATE_LABELS = {
        "draft": "Not opened",
        "open": "Open for nomination",
        "nominated": "Awaiting federation review",
        "confirmed": "Confirmed",
        "rejected": "Needs new nominee",
        "cancelled": "Cancelled",
    }

    def get_portal_state_label(self):
        self.ensure_one()
        return self._PORTAL_DUTY_STATE_LABELS.get(
            self.state, self._portal_label_from_selection("state")
        )


class FederationPlayer(models.Model):
    _inherit = ["federation.player", "federation.portal.label.mixin"]

    _PORTAL_PLAYER_STATE_LABELS = {
        "active": "Active",
        "inactive": "Inactive",
        "suspended": "Suspended",
        "retired": "Retired",
    }

    def get_portal_state_label(self):
        self.ensure_one()
        return self._PORTAL_PLAYER_STATE_LABELS.get(
            self.state, self._portal_label_from_selection("state")
        )


class FederationPlayerLicense(models.Model):
    _inherit = ["federation.player.license", "federation.portal.label.mixin"]

    _PORTAL_LICENSE_STATE_LABELS = {
        "active": "Active",
        "cancelled": "Cancelled",
        "expired": "Expired",
        "revoked": "Cancelled",
        "draft": "Draft",
    }

    def get_portal_state_label(self):
        self.ensure_one()
        return self._PORTAL_LICENSE_STATE_LABELS.get(
            self.state, self._portal_label_from_selection("state")
        )
