from odoo import models

PUBLIC_TOURNAMENT_STATE_LABELS = {
    "draft": "Planning",
    "open": "Open for entries",
    "in_progress": "Happening now",
    "closed": "Completed",
    "cancelled": "Cancelled",
}

PUBLIC_EDITION_STATE_LABELS = {
    "draft": "Upcoming",
    "open": "Upcoming",
    "in_progress": "In progress",
    "closed": "Completed",
    "cancelled": "Cancelled",
}

PUBLIC_OPERATIONAL_STATUS_LABELS = {
    "as_published": "Scheduled",
    "moved": "Updated time or court",
    "delayed": "Delayed",
    "postponed": "Postponed",
    "cancelled": "Cancelled",
}

PUBLIC_MATCH_STATE_LABELS = {
    "draft": "Awaiting kickoff",
    "scheduled": "Scheduled",
    "in_progress": "Live",
    "done": "Final",
    "cancelled": "Cancelled",
}

PUBLIC_PARTICIPANT_STATE_LABELS = {
    "registered": "Entry received",
    "confirmed": "Confirmed",
    "withdrawn": "Withdrawn",
}

PUBLIC_LICENSE_STATE_LABELS = {
    "active": "Active",
    "cancelled": "Cancelled",
    "expired": "Expired",
    "revoked": "Cancelled",
    "draft": "Draft",
}


class FederationCompetitionEdition(models.Model):
    _inherit = "federation.competition.edition"

    def get_public_site_state_label(self):
        """Return the audience-facing competition status."""
        self.ensure_one()
        selection_label = dict(self._fields["state"].selection).get(
            self.state, self.state or ""
        )
        return PUBLIC_EDITION_STATE_LABELS.get(self.state, selection_label)


class FederationTournament(models.Model):
    _inherit = "federation.tournament"

    def get_public_site_state_label(self):
        """Return the audience-facing state label for public website pages."""
        self.ensure_one()
        selection_label = dict(self._fields["state"].selection).get(
            self.state, self.state or ""
        )
        return PUBLIC_TOURNAMENT_STATE_LABELS.get(self.state, selection_label)


class FederationMatch(models.Model):
    _inherit = "federation.match"

    def get_public_site_state_label(self):
        """Return the audience-facing match status label for public pages."""
        self.ensure_one()
        selection_label = dict(self._fields["state"].selection).get(
            self.state, self.state or ""
        )
        return PUBLIC_MATCH_STATE_LABELS.get(self.state, selection_label)

    def get_public_operational_status_label(self):
        """Translate match-day scheduling changes for spectators."""
        self.ensure_one()
        return PUBLIC_OPERATIONAL_STATUS_LABELS.get(
            self.operational_status, "Scheduled"
        )


class FederationTournamentParticipant(models.Model):
    _inherit = "federation.tournament.participant"

    def get_public_site_state_label(self):
        """Return the audience-facing participant status label for public pages."""
        self.ensure_one()
        selection_label = dict(self._fields["state"].selection).get(
            self.state, self.state or ""
        )
        return PUBLIC_PARTICIPANT_STATE_LABELS.get(self.state, selection_label)


class FederationPlayerLicense(models.Model):
    _inherit = "federation.player.license"

    def get_public_site_state_label(self):
        """Return the audience-facing license status label for public pages."""
        self.ensure_one()
        selection_label = dict(self._fields["state"].selection).get(
            self.state, self.state or ""
        )
        return PUBLIC_LICENSE_STATE_LABELS.get(self.state, selection_label)
