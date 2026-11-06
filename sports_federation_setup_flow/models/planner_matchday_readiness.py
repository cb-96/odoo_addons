from odoo import models


class FederationCompetitionEditionMatchdayReadiness(models.Model):
    _inherit = "federation.competition.edition"

    def get_planner_matchday_readiness(self):
        """Answer "can the next game day run?" for the competition planner.

        The answer comes from the one authoritative match-day readiness
        service. It is loaded separately from the planner data so the cheap
        setup guidance computed for lists never pays for it. Roles that cannot
        read every checked area get an explicit "unavailable" answer instead of
        a partial one.
        """
        self.ensure_one()
        self.check_access("read")
        access = self._usability_operation_access()
        if not all(
            access[key] for key in ("matchdays", "rosters", "lineups", "officials")
        ):
            return {"available": False, "readiness": False}
        day = self.env["federation.matchday"].search(
            [
                ("edition_id", "=", self.id),
                ("state", "not in", ("cancelled", "closed")),
            ],
            order="date,id",
            limit=1,
        )
        if not day:
            return {"available": True, "readiness": False}
        return {
            "available": True,
            "readiness": self.env["federation.matchday.readiness"].evaluate(day),
        }
