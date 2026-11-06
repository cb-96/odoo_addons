from odoo import models


class FederationSeason(models.Model):
    _inherit = "federation.season"

    def write(self, vals):
        result = super().write(vals)
        if vals.get("state") in ("closed", "cancelled") or vals.get("active") is False:
            self._portal_close_active_rosters()
        return result

    def _portal_close_active_rosters(self):
        """Close the active rosters of seasons that are over.

        Rosters only exist to prepare game days. Once their season is closed,
        cancelled or archived there is nothing left to prepare, so they are
        closed with the usual audit event instead of staying "Active" forever.
        Nothing is deleted and a roster can still be reopened by its club.
        """
        rosters = (
            self.env["federation.team.roster"]
            .sudo()
            .search([("season_id", "in", self.ids), ("status", "=", "active")])
        )
        if rosters:
            rosters.action_close()
        return rosters
