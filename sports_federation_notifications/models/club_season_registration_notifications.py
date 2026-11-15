from odoo import models


class FederationClubSeasonRegistrationNotifications(models.Model):
    """Tell federation managers when a club submits its season player list."""

    _inherit = "federation.club.season.registration"

    def _season_players_dispatcher(self):
        # Clubs submit from the portal; resolving the manager group and
        # creating their activities is a system effect of that submission.
        dispatcher = self.env.get("federation.notification.dispatcher")
        return dispatcher.sudo() if dispatcher is not None else None

    def action_submit(self):
        # A list that is already submitted keeps its open approval activities.
        newly_submitted = self.filtered(lambda rec: rec.state != "submitted")
        result = super().action_submit()
        dispatcher = self._season_players_dispatcher()
        if dispatcher is not None:
            for registration in newly_submitted:
                dispatcher.send_season_players_submitted(registration)
        return result

    def action_confirm(self):
        result = super().action_confirm()
        self._close_season_players_review("Season players approved.")
        return result

    def action_cancel(self):
        result = super().action_cancel()
        self._close_season_players_review("Season player registration cancelled.")
        return result

    def _close_season_players_review(self, feedback):
        dispatcher = self._season_players_dispatcher()
        if dispatcher is not None:
            for registration in self:
                dispatcher.close_season_players_review(registration, feedback)
