"""Give every court a named operator when a game day opens.

Assigning operators court by court was a mandatory step before any score could
be entered.  When the day opens, each court without an active operator now gets
the competition's match-day manager (or competition director, or the person who
opened the day).  Managers can still deactivate and reassign operators; every
assignment stays a named, internal, auditable record.
"""

from odoo import models


class CourtDefaultOperators(models.AbstractModel):
    _inherit = "federation.matchday.commands"

    def _open_matchday(self, matchday_id):
        result = super()._open_matchday(matchday_id)
        matchday = self.env["federation.matchday"].browse(int(matchday_id)).exists()
        if matchday:
            self._assign_default_court_operators(matchday)
        return result

    def _default_court_operator(self, matchday):
        roles = self.env["federation.competition.role.assignment"].sudo()
        for role in ("matchday_manager", "competition_director"):
            assignment = roles.search(
                [
                    ("edition_id", "=", matchday.edition_id.id),
                    ("role", "=", role),
                    ("active", "=", True),
                    ("user_id.share", "=", False),
                ],
                order="id",
                limit=1,
            )
            if assignment:
                return assignment.user_id
        user = self.env.user
        if not self.env.su and not user.share:
            return user
        return self.env["res.users"]

    def _assign_default_court_operators(self, matchday):
        operator = self._default_court_operator(matchday)
        if not operator:
            return
        Access = (
            self.env["federation.court.access"]
            .sudo()
            .with_context(court_default_operator=True, active_test=False)
        )
        courts = (
            matchday.sudo()
            .slot_ids.mapped("court_id")
            .filtered(lambda court: court.venue_id == matchday.venue_id)
        )
        existing = Access.search([("matchday_id", "=", matchday.id)])
        covered = existing.filtered("active").mapped("court_id")
        assigned_pairs = {(item.court_id.id, item.user_id.id) for item in existing}
        values = [
            {"matchday_id": matchday.id, "court_id": court.id, "user_id": operator.id}
            for court in courts - covered
            if (court.id, operator.id) not in assigned_pairs
        ]
        if values:
            Access.create(values)
