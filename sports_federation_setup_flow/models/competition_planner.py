from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class FederationCompetitionEditionPlanner(models.Model):
    _inherit = "federation.competition.edition"

    _PLANNER_STEP_MODELS = {
        "teams": ("federation.registration.window", "list,form"),
        "format": ("federation.competition.structure", "list,form"),
        "gamedays": ("federation.matchday", "calendar,list,form"),
        "schedule": ("federation.schedule", "list,form"),
        # Publication remains an action on the governed schedule. Keeping the
        # approver on that record preserves the existing command boundary.
        "publication": ("federation.schedule", "list,form"),
    }

    def action_open_competition_planner(self):
        self.ensure_one()
        self.check_access("read")
        return {
            "type": "ir.actions.client",
            "name": _("Competition Planner"),
            "tag": "sports_federation_setup_flow.CompetitionPlanner",
            "params": {"edition_id": self.id},
            "target": "current",
        }

    def action_continue_setup(self):
        """Make the visual planner the ordinary setup entry point.

        Technical workspaces and their command services remain authoritative;
        the planner only projects readiness and opens the owning records.
        """
        return self.action_open_competition_planner()

    def action_open_planner_step(self, step):
        self.ensure_one()
        self.check_access("read")
        if step == "basics":
            return self.action_setup_teams_and_format() if not self.tournament_ids else self.get_formview_action()
        simplified_actions = {
            "teams": self.action_setup_teams_and_format,
            "format": self.action_setup_teams_and_format,
            "gamedays": self.action_setup_gamedays,
            "schedule": self.action_setup_schedule,
            "publication": self.action_setup_publication,
        }
        if step in simplified_actions:
            return simplified_actions[step]()
        if step not in self._PLANNER_STEP_MODELS:
            raise ValidationError(_("Unknown competition planner step: %s") % step)

        model_name, view_mode = self._PLANNER_STEP_MODELS[step]
        model = self.env[model_name]
        model.check_access_rights("read")
        action = {
            "type": "ir.actions.act_window",
            "name": self._planner_step_label(step),
            "res_model": model_name,
            "view_mode": view_mode,
            "views": [(False, view_type) for view_type in view_mode.split(",")],
            "target": "current",
            "domain": [("edition_id", "=", self.id)],
            "context": {
                "default_edition_id": self.id,
                "search_default_edition_id": self.id,
                "competition_planner_edition_id": self.id,
            },
        }
        return action

    def _planner_record_action(self, record, name=None):
        record.ensure_one()
        record.check_access("read")
        return {
            "type": "ir.actions.act_window",
            "name": name or record.display_name,
            "res_model": record._name,
            "res_id": record.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
            "context": {
                "competition_planner_edition_id": self.id,
                "default_edition_id": self.id,
            },
        }

    def _planner_issue_action(self, issue):
        """Resolve a server-produced blocker to its smallest useful workspace."""
        key = issue["key"]
        if key == "missing-divisions":
            return self.action_setup_teams_and_format()
        if key == "unallocated-fixtures":
            has_days = self.env["federation.matchday"].search_count(
                [("edition_id", "=", self.id), ("state", "!=", "cancelled")]
            )
            return self.action_setup_schedule() if has_days else self.action_setup_gamedays()
        if key == "missing-scheduled-days":
            return self.action_setup_gamedays()

        parts = key.split("-")
        record_id = int(parts[1]) if len(parts) > 2 and parts[1].isdigit() else False
        if key.startswith("division-") and record_id:
            division = self.env["federation.tournament"].browse(record_id).exists()
            if not division or division.edition_id != self:
                raise ValidationError(_("This planner item no longer belongs to the competition."))
            if key.endswith(("-teams", "-team-count")):
                if self.env.user.has_group(
                    "sports_federation_base.group_federation_advanced_operator"
                ):
                    window = self.env["federation.registration.window"].search(
                        [
                            ("edition_id", "=", self.id),
                            ("division_id", "=", division.id),
                        ],
                        order="id desc",
                        limit=1,
                    )
                    if window:
                        return self._planner_record_action(window)
                return self.action_setup_teams_and_format()
            structure = self.env["federation.competition.structure"].search(
                [("edition_id", "=", self.id), ("division_id", "=", division.id)],
                order="version desc,id desc", limit=1,
            )
            return (
                self._planner_record_action(structure)
                if structure and self.env.user.has_group(
                    "sports_federation_base.group_federation_advanced_operator"
                )
                else self.action_setup_teams_and_format()
            )
        if key.startswith("gameday-") and record_id:
            day = self.env["federation.matchday"].browse(record_id).exists()
            if not day or day.edition_id != self:
                raise ValidationError(_("This planner item no longer belongs to the competition."))
            if key.endswith("-missing-schedule"):
                return self.action_setup_schedule()
            if key.endswith(("-cancelled", "-capacity", "-not-ready")):
                return self.action_setup_gamedays()
            if key.endswith(("-missing-publication", "-stale-publication")):
                schedule = self.env["federation.schedule"].search(
                    [("edition_id", "=", self.id), ("matchday_id", "=", day.id)],
                    order="revision desc,id desc", limit=1,
                )
                if not schedule or schedule.state in ("draft", "changes_requested", "approved"):
                    # One command publishes every ready game day.
                    return self.action_setup_publication()
                if schedule:
                    review_model = self.env.get("federation.schedule.review")
                    review = False
                    if review_model is not None:
                        review = review_model.sudo().search(
                            [
                                ("schedule_id", "=", schedule.id),
                                ("submitted_revision", "=", schedule.revision),
                                ("state", "in", ("pending", "approved")),
                            ],
                            order="id desc",
                            limit=1,
                        )
                    if review:
                        review = review.with_env(self.env)
                        try:
                            review.check_access("read")
                        except AccessError:
                            review = self.env["federation.schedule.review"]
                        if review:
                            return self._planner_record_action(
                                review, _("Schedule review")
                            )
                    return self._planner_record_action(schedule)
            return self._planner_record_action(day)
        if key.startswith("schedule-") and record_id:
            schedule = self.env["federation.schedule"].browse(record_id).exists()
            if not schedule or schedule.edition_id != self:
                raise ValidationError(_("This planner item no longer belongs to the competition."))
            return self._planner_record_action(schedule)
        return self.action_open_planner_step(issue["step"])

    def _action_open_team_selection(self, division):
        wizard = self.env["federation.competition.team.selection.wizard"].create(
            {"edition_id": self.id, "division_id": division.id}
        )
        wizard._onchange_division_id()
        return {
            "type": "ir.actions.act_window",
            "name": _("Select Teams"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
        }

    def _action_open_format_selection(self, division):
        participant_set = self.env["federation.participant.set"].search(
            [
                ("edition_id", "=", self.id),
                ("division_id", "=", division.id),
                ("state", "=", "finalized"),
            ],
            order="id desc",
            limit=1,
        )
        if not participant_set:
            return self._action_open_team_selection(division)
        wizard = self.env["federation.competition.format.setup.wizard"].create(
            {
                "edition_id": self.id,
                "division_id": division.id,
                "participant_set_id": participant_set.id,
                "format_type": self.setup_default_format_type,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Choose Format"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
        }

    def action_open_planner_issue(self, issue_key):
        self.ensure_one()
        self.check_access("read")
        issue = next(
            (
                item
                for item in self.get_competition_planner_data()["issues"]
                if item["key"] == issue_key
            ),
            None,
        )
        if not issue:
            raise ValidationError(_("This blocker was resolved or changed. Refresh the planner."))
        return self._planner_issue_action(issue)

    def action_open_planner_operation(self, operation):
        self.ensure_one()
        self.check_access("read")
        tasks = self._usability_pending_tasks()
        if operation == "rosters" and tasks["rosters"]:
            team = self.env["federation.team"].browse(tasks["rosters"][0])
            division = self.tournament_ids.filtered(
                lambda d: team in self._usability_division_teams(d)
            )[:1]
            return team._ensure_tournament_roster(division).get_formview_action()
        if operation == "lineups" and tasks["lineups"]:
            day = self.env["federation.matchday"].browse(tasks["lineups"][0])
            return day.action_prepare_lineups()
        if operation == "officials" and tasks["officials"]:
            match = self.env["federation.match"].browse(tasks["officials"][0])
            day = match.schedule_publication_id.matchday_id
            if day:
                action = self.env.ref(
                    "sports_federation_officiating.action_matchday_assign_official_wizard"
                ).read()[0]
                action["context"] = {"default_matchday_id": day.id}
                return action
            return match.action_view_referee_assignments()
        allowed = {
            "matchdays": ("federation.matchday", "calendar,list,form", _("Match days")),
            "schedules": ("federation.schedule", "list,form", _("Schedules")),
            "rosters": ("federation.team.roster", "list,form", _("Roster readiness")),
            "lineups": ("federation.match.sheet", "list,form", _("Game-day lineups")),
            "officials": ("federation.match.referee", "list,form", _("Official coverage")),
            "results": ("federation.match", "list,form", _("Result follow-up")),
        }
        if operation not in allowed:
            raise ValidationError(_("Unknown competition operation: %s") % operation)
        model_name, view_mode, name = allowed[operation]
        model = self.env.get(model_name)
        if model is None or not model.check_access_rights("read", raise_exception=False):
            raise ValidationError(_("This operation is not available to your role."))
        if operation in ("matchdays", "schedules"):
            domain = [("edition_id", "=", self.id)]
            if operation == "matchdays":
                domain.append(("state", "not in", ("closed", "cancelled")))
        elif operation == "rosters":
            domain = [("team_id", "in", tasks["rosters"]), ("season_id", "=", self.season_id.id)]
        elif operation == "lineups":
            domain = [("match_id.schedule_publication_id.matchday_id", "in", tasks["lineups"]), ("state", "in", ("draft", "submitted"))]
        elif operation == "officials":
            domain = [("match_id", "in", tasks["officials"]), ("state", "not in", ("confirmed", "done", "cancelled"))]
        else:
            domain = [("id", "in", tasks["results"])]
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model_name,
            "view_mode": view_mode,
            "views": self._usability_operation_views(operation, view_mode),
            "domain": domain,
            "context": {"default_edition_id": self.id, "competition_planner_edition_id": self.id},
            "target": "current",
        }

    def action_open_planner_advanced(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "sports_federation_base.group_federation_advanced_operator"
        ):
            raise ValidationError(_("Advanced competition tools are not enabled for your role."))
        return self.action_open_advanced_workspace()

    def action_open_planner_administration(self):
        self.ensure_one()
        if not self.env.user.has_group(
            "sports_federation_base.group_federation_advanced_operator"
        ):
            raise ValidationError(_("Administration tools are not enabled for your role."))
        Task = self.env.get("federation.operation.task")
        if Task is not None and Task.check_access_rights("read", raise_exception=False):
            action = self.env["ir.actions.act_window"]._for_xml_id(
                "sports_federation_portal.action_federation_operation_task"
            )
            action["domain"] = [
                ("season_id", "=", self.season_id.id),
                ("state", "!=", "done"),
            ]
            return action
        return self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_base.action_federation_operation_job"
        )







    def _usability_operation_views(self, operation, view_mode):
        if operation == "matchdays":
            return [(False, "calendar"), (False, "list"), (self.env.ref("sports_federation_setup_flow.matchday_focus_form").id, "form")]
        if operation == "results":
            return [(self.env.ref("sports_federation_setup_flow.result_focus_list").id, "list"), (False, "form")]
        return [(False, kind) for kind in view_mode.split(",")]

    def _usability_roster_checks_available(self):
        required_models = (
            self.env.get("federation.team.roster"),
            self.env.get("federation.participant.set"),
            self.env.get("federation.participant.set.line"),
        )
        return all(self._usability_model_can_read(model) for model in required_models)

    @staticmethod
    def _usability_model_can_read(model):
        if model is None:
            return False
        try:
            model.check_access("read")
        except AccessError:
            return False
        return True

    def _usability_operation_access(self):
        def can_read(model_name):
            model = self.env.get(model_name)
            return self._usability_model_can_read(model)

        matchday_access = can_read("federation.matchday")
        match_access = can_read("federation.match")
        return {
            "rosters": self._usability_roster_checks_available(),
            "lineups": (
                matchday_access
                and match_access
                and can_read("federation.match.sheet")
            ),
            "officials": (
                matchday_access
                and match_access
                and can_read("federation.match.referee")
            ),
            "results": match_access,
            "matchdays": matchday_access,
        }

    def _usability_pending_tasks(self):
        """Read-only caller-scoped task identities shared by badges and actions."""
        self.ensure_one()
        self.check_access("read")
        tasks = {key: [] for key in ("rosters", "lineups", "officials", "results")}
        divisions = self.tournament_ids
        operation_access = self._usability_operation_access()
        if operation_access["rosters"]:
            for division in divisions:
                for team in self._usability_division_teams(division):
                    roster = team._get_preferred_roster(self.season_id, competition=self.competition_id, statuses=("active", "draft"))
                    if not roster or roster.status != "active" or not roster.ready_for_activation:
                        tasks["rosters"].append(team.id)
        days = self.env["federation.matchday"].browse()
        if operation_access["matchdays"]:
            days = self.env["federation.matchday"].search([
                ("edition_id", "=", self.id), ("state", "in", ("scheduled", "open"))
            ], order="date,id")
        sheet_model = self.env.get("federation.match.sheet")
        if operation_access["lineups"]:
            for day in days:
                matches = day.published_match_ids.filtered(lambda m: m.state not in ("done", "cancelled"))
                sheets = sheet_model.search([("match_id", "in", matches.ids)])
                expected = {(m.id, t.id) for m in matches for t in (m.home_team_id | m.away_team_id)}
                approved = {(s.match_id.id, s.team_id.id) for s in sheets if s.state in ("approved", "locked")}
                if expected - approved:
                    tasks["lineups"].append(day.id)
        match_model = self.env.get("federation.match")
        if operation_access["results"]:
            # An approved result finishes the match, so pending results are
            # the ones submitted but not yet approved.
            tasks["results"] = match_model.search([
                ("tournament_id", "in", divisions.ids), ("state", "!=", "cancelled"),
                ("result_state", "in", ("submitted", "verified", "contested", "corrected")),
            ], order="date_scheduled,id").ids
        if operation_access["officials"]:
            tasks["officials"] = days.mapped("published_match_ids").filtered(
                lambda m: m.state not in ("done", "cancelled") and not m.is_officially_ready
            ).ids
        tasks["rosters"] = list(dict.fromkeys(tasks["rosters"]))
        return tasks

    def _usability_division_teams(self, division):
        participant_set = self.env["federation.participant.set"].search([
            ("edition_id", "=", self.id), ("division_id", "=", division.id), ("state", "=", "finalized")
        ], order="id desc", limit=1)
        if participant_set:
            return participant_set.line_ids.mapped("team_id")
        return division.participant_ids.filtered(lambda p: p.state != "withdrawn").mapped("team_id")
