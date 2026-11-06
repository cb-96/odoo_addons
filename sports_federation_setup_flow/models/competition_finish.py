"""Guided end of a competition in the Competition Hub.

After operations the Hub keeps proposing one next action until the
competition is closed: close finished gamedays, freeze final tables, then
close the competition. Publishing on the website is proposed as soon as the
competition is open. Closing is refused while anything is unfinished.
"""

from odoo import _, models
from odoo.exceptions import AccessError, ValidationError

PENDING_RESULT_STATES = ("submitted", "verified", "contested", "corrected")


class FederationCompetitionEditionFinish(models.Model):
    _inherit = "federation.competition.edition"

    # ------------------------------------------------------------------
    # What still has to happen
    # ------------------------------------------------------------------
    def _finish_matches(self):
        return self.env["federation.match"].search(
            [("tournament_id", "in", self.tournament_ids.ids)]
        )

    def _finish_open_gamedays(self):
        return self.env["federation.matchday"].search(
            [
                ("edition_id", "=", self.id),
                ("state", "not in", ("closed", "cancelled")),
            ],
            order="date,id",
        )

    def _finish_closable_gamedays(self):
        """Opened gamedays whose published matches are all finished."""
        days = self._finish_open_gamedays().filtered(lambda day: day.state == "open")
        return days.filtered(
            lambda day: day.published_match_ids
            and all(m.state in ("done", "cancelled") for m in day.published_match_ids)
        )

    def _finish_tables(self):
        return self.env["federation.standing"].search(
            [("tournament_id", "in", self.tournament_ids.ids)]
        )

    def _finish_freezable_tables(self):
        return self._finish_tables().filtered(
            lambda table: table.state != "frozen" and table.finish_readiness == "review"
        )

    def _finish_unplaced_fixtures(self):
        return self.env["federation.fixture"].search(
            [
                ("edition_id", "=", self.id),
                ("structure_id.state", "in", ("generated", "frozen")),
                ("operational_match_id", "=", False),
                ("bye_team_id", "=", False),
                ("state", "not in", ("cancelled", "completed")),
            ]
        )

    def _get_close_blockers(self):
        blockers = super()._get_close_blockers()
        matches = self._finish_matches()
        unfinished = matches.filtered(lambda m: m.state not in ("done", "cancelled"))
        if unfinished:
            blockers.append(
                _("%(count)s match(es) are not finished.", count=len(unfinished))
            )
        if "result_state" in matches._fields:
            pending = matches.filtered(
                lambda m: m.result_state in PENDING_RESULT_STATES
            )
            if pending:
                blockers.append(
                    _("%(count)s result(s) still need approval.", count=len(pending))
                )
        days = self._finish_open_gamedays()
        if days:
            blockers.append(
                _("Close or cancel these gamedays: %(days)s.")
                % {"days": ", ".join(days.mapped("display_name"))}
            )
        Incident = self.env.get("federation.matchday.incident")
        if Incident is not None:
            open_incidents = Incident.search_count(
                [
                    ("matchday_id.edition_id", "=", self.id),
                    ("resolved", "=", False),
                ]
            )
            if open_incidents:
                blockers.append(
                    _(
                        "%(count)s gameday incident(s) are unresolved.",
                        count=open_incidents,
                    )
                )
        waiting = self._finish_unplaced_fixtures()
        if waiting:
            blockers.append(
                _(
                    "%(count)s fixture(s) still wait for their teams.",
                    count=len(waiting),
                )
            )
        unfrozen = self._finish_tables().filtered(lambda table: table.state != "frozen")
        if unfrozen:
            blockers.append(
                _("Freeze these final tables: %(tables)s.")
                % {"tables": ", ".join(unfrozen.mapped("display_name"))}
            )
        return blockers

    # ------------------------------------------------------------------
    # Hub next actions
    # ------------------------------------------------------------------
    def _planner_finish_actions(self):
        """(key, count, label) entries appended to the Hub operations."""
        self.ensure_one()
        if self.state not in ("open", "in_progress"):
            return []
        actions = []
        if "website_published" in self._fields:
            actions.append(
                (
                    "publish_website",
                    0 if self.website_published else 1,
                    _("Publish the competition on the website"),
                )
            )
        can_read = self._usability_model_can_read
        if can_read(self.env.get("federation.matchday")) and can_read(
            self.env.get("federation.match")
        ):
            actions.append(
                (
                    "finish_matchdays",
                    len(self._finish_closable_gamedays()),
                    _("Close finished gamedays"),
                )
            )
        if can_read(self.env.get("federation.standing")):
            actions.append(
                (
                    "finish_tables",
                    len(self._finish_freezable_tables()),
                    _("Freeze final tables"),
                )
            )
        close_models = (
            "federation.match",
            "federation.matchday",
            "federation.matchday.incident",
            "federation.fixture",
            "federation.standing",
        )
        can_close = all(
            can_read(self.env.get(model_name)) for model_name in close_models
        )
        if can_close:
            try:
                self.check_access("write")
            except AccessError:
                can_close = False
        if can_close:
            ready_to_close = (
                self.state == "in_progress" and not self._get_close_blockers()
            )
            actions.append(
                (
                    "close_competition",
                    1 if ready_to_close else 0,
                    _("Close the competition"),
                )
            )
        return actions

    def action_open_planner_operation(self, operation):
        self.ensure_one()
        if operation == "publish_website":
            self.check_access("read")
            return self.get_formview_action()
        if operation == "finish_matchdays":
            self.check_access("read")
            day = self._finish_closable_gamedays()[:1]
            if not day:
                raise ValidationError(_("No finished gameday is waiting to be closed."))
            return day.get_formview_action()
        if operation in ("finish_tables", "final_tables"):
            self.check_access("read")
            tables = self._finish_tables()
            return {
                "type": "ir.actions.act_window",
                "name": _("Final tables"),
                "res_model": "federation.standing",
                "view_mode": "list,form",
                "domain": [("id", "in", tables.ids)],
                "target": "current",
            }
        if operation == "close_competition":
            self.check_access("write")
            self.transition_competition_state(
                "closed", reason=_("Closed from the Competition Hub.")
            )
            return self.get_formview_action()
        return super().action_open_planner_operation(operation)
