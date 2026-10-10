from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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
            return self.action_setup_divisions() if not self.tournament_ids else self.get_formview_action()
        simplified_actions = {
            "teams": self.action_setup_participants,
            "format": self.action_setup_format,
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
            return self.action_setup_divisions()
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
                window = self.env["federation.registration.window"].search(
                    [("edition_id", "=", self.id), ("division_id", "=", division.id)],
                    order="id desc", limit=1,
                )
                return (
                    self._planner_record_action(window)
                    if window and self.env.user.has_group(
                        "sports_federation_base.group_federation_advanced_operator"
                    )
                    else self._action_open_team_selection(division)
                )
            structure = self.env["federation.competition.structure"].search(
                [("edition_id", "=", self.id), ("division_id", "=", division.id)],
                order="version desc,id desc", limit=1,
            )
            return (
                self._planner_record_action(structure)
                if structure and self.env.user.has_group(
                    "sports_federation_base.group_federation_advanced_operator"
                )
                else self._action_open_format_selection(division)
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
                if schedule:
                    review_model = self.env.get("federation.schedule.review")
                    review = review_model and review_model.search(
                        [("schedule_id", "=", schedule.id)], order="id desc", limit=1
                    )
                    if review:
                        return self._planner_record_action(review, _("Schedule review"))
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
        if operation == "lineups":
            day = self.env["federation.matchday"].search(
                [
                    ("edition_id", "=", self.id),
                    ("state", "in", ("scheduled", "open")),
                ],
                order="date,id",
                limit=1,
            )
            if day and hasattr(day, "action_prepare_lineups"):
                return day.action_prepare_lineups()
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
        division_ids = self.tournament_ids.ids
        if operation in ("matchdays", "schedules"):
            domain = [("edition_id", "=", self.id)]
        elif operation == "rosters":
            domain = [
                ("season_id", "=", self.season_id.id),
                ("competition_id", "=", self.competition_id.id),
            ]
        elif operation == "lineups":
            domain = [
                ("match_id.tournament_id", "in", division_ids),
                ("state", "in", ("draft", "submitted")),
            ]
        elif operation == "officials":
            domain = [("tournament_id", "in", division_ids), ("state", "!=", "cancelled")]
        else:
            domain = [("tournament_id", "in", division_ids), ("result_state", "!=", "approved")]
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": model_name,
            "view_mode": view_mode,
            "views": [(False, view_type) for view_type in view_mode.split(",")],
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

    def _planner_enrich_issues(self, issues):
        owners = {
            "basics": _("Competition director"),
            "teams": _("Registration manager"),
            "format": _("Format manager"),
            "gamedays": _("Calendar planner"),
            "schedule": _("Schedule planner"),
            "publication": _("Schedule approver"),
        }
        labels = {
            "basics": _("Edit competition"),
            "teams": _("Select teams"),
            "format": _("Choose format"),
            "gamedays": _("Define game days"),
            "schedule": _("Plan competition"),
            "publication": _("Open review"),
        }
        for issue in issues:
            issue["owner"] = owners[issue["step"]]
            issue["action_label"] = labels[issue["step"]]
        return issues

    @api.model
    def _planner_step_label(self, step):
        return {
            "basics": _("Competition"),
            "teams": _("Teams"),
            "format": _("Format"),
            "gamedays": _("Dates & venues"),
            "schedule": _("Schedule"),
            "publication": _("Review & publish"),
        }[step]

    def _planner_division_rows(self, windows, structures):
        rows = []
        issues = []
        current_structures = self.env["federation.competition.structure"]
        windows_by_division = defaultdict(lambda: self.env["federation.registration.window"])
        structures_by_division = defaultdict(
            lambda: self.env["federation.competition.structure"]
        )
        for window in windows:
            windows_by_division[window.division_id.id] |= window
        for structure in structures:
            structures_by_division[structure.division_id.id] |= structure

        for division in self.tournament_ids.sorted(lambda item: (item.name or "", item.id)):
            division_windows = windows_by_division[division.id]
            participant_sets = division_windows.mapped("participant_set_id").filtered(
                lambda item: item.state == "finalized"
            ).sorted(lambda item: item.id, reverse=True)
            participant_set = participant_sets[:1]
            team_count = len(participant_set.mapped("line_ids.team_id"))
            division_structures = structures_by_division[division.id]
            current_structure = division_structures.sorted(
                lambda item: (item.version, item.id), reverse=True
            )[:1]
            if current_structure:
                current_structures |= current_structure

            teams_ready = bool(participant_set and team_count >= 2)
            format_ready = bool(
                teams_ready
                and current_structure
                and current_structure.state == "frozen"
                and current_structure.participant_set_id == participant_set
                and current_structure.fixture_ids.filtered(
                    lambda item: item.state != "cancelled"
                )
            )
            teams_status = "complete" if teams_ready else "attention"
            format_status = "complete" if format_ready else "blocked"
            if not participant_set:
                issues.append(
                    {
                        "key": "division-%s-teams" % division.id,
                        "step": "teams",
                        "severity": "blocking",
                        "title": division.display_name,
                        "message": _("Finalize the participating teams for this division."),
                    }
                )
            elif team_count < 2:
                issues.append(
                    {
                        "key": "division-%s-team-count" % division.id,
                        "step": "teams",
                        "severity": "blocking",
                        "title": division.display_name,
                        "message": _(
                            "Finalize at least two participating teams for this division."
                        ),
                    }
                )
            elif not current_structure:
                issues.append(
                    {
                        "key": "division-%s-format" % division.id,
                        "step": "format",
                        "severity": "blocking",
                        "title": division.display_name,
                        "message": _("Choose and generate a competition format."),
                    }
                )
            elif current_structure.state != "frozen":
                issues.append(
                    {
                        "key": "division-%s-freeze" % division.id,
                        "step": "format",
                        "severity": "blocking",
                        "title": division.display_name,
                        "message": _("Review and freeze the latest generated format."),
                    }
                )
            elif current_structure.participant_set_id != participant_set:
                issues.append(
                    {
                        "key": "division-%s-stale-format" % division.id,
                        "step": "format",
                        "severity": "blocking",
                        "title": division.display_name,
                        "message": _(
                            "Rebuild the format from the latest finalized participant set."
                        ),
                    }
                )
            elif not current_structure.fixture_ids.filtered(
                lambda item: item.state != "cancelled"
            ):
                issues.append(
                    {
                        "key": "division-%s-no-fixtures" % division.id,
                        "step": "format",
                        "severity": "blocking",
                        "title": division.display_name,
                        "message": _("Generate at least one playable fixture."),
                    }
                )

            rows.append(
                {
                    "id": division.id,
                    "name": division.display_name,
                    "team_count": team_count,
                    "teams_status": teams_status,
                    "format_status": format_status,
                    "format_name": current_structure.display_name or False,
                    "ready": teams_ready and format_ready,
                }
            )
        return rows, issues, current_structures.filtered(
            lambda item: item.state == "frozen"
        )

    def _planner_global_issues(self, gamedays, schedules, expected_fixtures):
        issues = []
        allocated_fixtures = gamedays.mapped("allocation_ids.fixture_ids").filtered(
            lambda item: item.state != "cancelled"
        )
        unallocated_fixtures = expected_fixtures - allocated_fixtures
        if unallocated_fixtures:
            issues.append(
                {
                    "key": "unallocated-fixtures",
                    "step": "gamedays",
                    "severity": "blocking",
                    "title": _("Fixture allocation"),
                    "message": _(
                        "Allocate all %(count)s playable fixtures to game days.",
                        count=len(unallocated_fixtures),
                    ),
                }
            )

        scheduled_days = self.env["federation.matchday"]
        for gameday in gamedays.sorted(lambda item: (item.date, item.id)):
            day_fixtures = gameday.allocation_ids.mapped("fixture_ids").filtered(
                lambda item: item.state != "cancelled"
            )
            if not day_fixtures:
                continue
            scheduled_days |= gameday
            if gameday.state == "cancelled":
                issues.append(
                    {
                        "key": "gameday-%s-cancelled" % gameday.id,
                        "step": "gamedays",
                        "severity": "blocking",
                        "title": gameday.display_name,
                        "message": _(
                            "Move this division's fixtures to an active game day."
                        ),
                    }
                )
                continue
            if not gameday.playable_slot_count or gameday.spare_capacity < 0:
                issues.append(
                    {
                        "key": "gameday-%s-capacity" % gameday.id,
                        "step": "gamedays",
                        "severity": "blocking",
                        "title": gameday.display_name,
                        "message": _(
                            "Add playable court capacity or reduce allocated fixtures."
                        ),
                    }
                )
            if gameday.state not in ("capacity_ready", "scheduled", "open", "closed"):
                issues.append(
                    {
                        "key": "gameday-%s-not-ready" % gameday.id,
                        "step": "gamedays",
                        "severity": "blocking",
                        "title": gameday.display_name,
                        "message": _("Mark the game-day capacity ready before scheduling."),
                    }
                )

            schedule = schedules.filtered(
                lambda item: item.matchday_id == gameday and item.state != "superseded"
            )[:1]
            if not schedule:
                issues.append(
                    {
                        "key": "gameday-%s-missing-schedule" % gameday.id,
                        "step": "schedule",
                        "severity": "blocking",
                        "title": gameday.display_name,
                        "message": _("Generate a working schedule for this game day."),
                    }
                )
            else:
                if schedule.unassigned_fixture_count:
                    issues.append(
                        {
                            "key": "schedule-%s-unassigned" % schedule.id,
                            "step": "schedule",
                            "severity": "blocking",
                            "title": schedule.display_name,
                            "message": _(
                                "Assign every allocated fixture before review."
                            ),
                        }
                    )
                if schedule.stale_assignment_count:
                    issues.append(
                        {
                            "key": "schedule-%s-stale" % schedule.id,
                            "step": "schedule",
                            "severity": "blocking",
                            "title": schedule.display_name,
                            "message": _(
                                "Remove assignments that are no longer in this game-day plan."
                            ),
                        }
                    )

            publication = gameday.current_publication_id
            if not publication or publication.state != "live":
                issues.append(
                    {
                        "key": "gameday-%s-missing-publication" % gameday.id,
                        "step": "publication",
                        "severity": "blocking",
                        "title": gameday.display_name,
                        "message": _(
                            "Complete review and publish this game day's schedule."
                        ),
                    }
                )
            elif (
                not schedule
                or publication.schedule_id != schedule
                or publication.source_revision != schedule.revision
                or schedule.state != "published"
            ):
                issues.append(
                    {
                        "key": "gameday-%s-stale-publication" % gameday.id,
                        "step": "publication",
                        "severity": "blocking",
                        "title": gameday.display_name,
                        "message": _(
                            "Publish the latest approved schedule revision for this game day."
                        ),
                    }
                )

        if expected_fixtures and not scheduled_days and not unallocated_fixtures:
            # Defensive fallback for a malformed allocation projection.
            issues.append(
                {
                    "key": "missing-scheduled-days",
                    "step": "gamedays",
                    "severity": "blocking",
                    "title": _("Game-day plan"),
                    "message": _("Allocate playable fixtures to at least one game day."),
                }
            )
        return issues

    def _planner_steps(self, counts, division_rows, issues, expected_fixtures):
        divisions_ready = bool(counts["divisions"])
        teams_ready = divisions_ready and all(
            row["teams_status"] == "complete" for row in division_rows
        )
        formats_ready = teams_ready and all(
            row["format_status"] == "complete" for row in division_rows
        )
        issue_counts = defaultdict(int)
        for issue in issues:
            issue_counts[issue["step"]] += 1
        scheduled_days = counts["scheduled_gamedays"]
        completion = {
            "basics": divisions_ready,
            "teams": teams_ready,
            "format": formats_ready,
            "gamedays": formats_ready
            and bool(expected_fixtures)
            and not issue_counts["gamedays"],
            "schedule": formats_ready
            and bool(scheduled_days)
            and not issue_counts["gamedays"]
            and not issue_counts["schedule"],
            "publication": formats_ready
            and bool(scheduled_days)
            and not issue_counts["gamedays"]
            and not issue_counts["schedule"]
            and not issue_counts["publication"],
        }
        for key in completion:
            completion[key] = completion[key] and not issue_counts[key]

        result = []
        first_incomplete_seen = False
        for key in ("basics", "teams", "format", "gamedays", "schedule", "publication"):
            complete = completion[key]
            if complete and not first_incomplete_seen:
                status = "complete"
            elif not first_incomplete_seen:
                status = "current"
                first_incomplete_seen = True
            else:
                status = "blocked"
            result.append(
                {
                    "key": key,
                    "label": self._planner_step_label(key),
                    "status": status,
                    "issue_count": issue_counts[key],
                    "complete": complete,
                }
            )
        return result

    def get_competition_planner_data(self):
        self.ensure_one()
        self.check_access("read")

        windows = self.env["federation.registration.window"].search(
            [("edition_id", "=", self.id)]
        )
        structures = self.env["federation.competition.structure"].search(
            [("edition_id", "=", self.id)]
        )
        gamedays = self.env["federation.matchday"].search(
            [("edition_id", "=", self.id)]
        )
        schedules = self.env["federation.schedule"].search(
            [("edition_id", "=", self.id)]
        )
        division_count, participant_count, gameday_count, schedule_count, publication_count = (
            self._setup_counts()
        )
        counts = {
            "divisions": division_count,
            "participants": participant_count,
            "gamedays": gameday_count,
            "schedules": schedule_count,
            "publications": publication_count,
        }
        division_rows, issues, frozen_structures = self._planner_division_rows(
            windows, structures
        )
        expected_fixtures = frozen_structures.mapped("fixture_ids").filtered(
            lambda item: item.state != "cancelled"
        )
        if not counts["divisions"]:
            issues.append(
                {
                    "key": "missing-divisions",
                    "step": "basics",
                    "severity": "blocking",
                    "title": _("Competition basics"),
                    "message": _("Add at least one division."),
                }
            )
        issues += self._planner_global_issues(gamedays, schedules, expected_fixtures)
        issues = self._planner_enrich_issues(issues)
        counts["scheduled_gamedays"] = len(
            gamedays.filtered(
                lambda item: bool(
                    item.allocation_ids.mapped("fixture_ids").filtered(
                        lambda fixture: fixture.state != "cancelled"
                    )
                )
            )
        )
        steps = self._planner_steps(counts, division_rows, issues, expected_fixtures)
        current = next((step for step in steps if step["status"] == "current"), steps[-1])
        current_issue = next(
            (issue for issue in issues if issue["step"] == current["key"]),
            issues[0] if issues else None,
        )
        next_matchday = gamedays.filtered(lambda day: day.state != "cancelled").sorted(
            lambda day: (day.date or fields.Date.to_date("9999-12-31"), day.id)
        )[:1]
        division_ids = self.tournament_ids.ids
        roster_model = self.env.get("federation.team.roster")
        lineup_model = self.env.get("federation.match.sheet")
        official_model = self.env.get("federation.match.referee")
        match_model = self.env.get("federation.match")
        roster_available = bool(
            roster_model is not None
            and roster_model.check_access_rights("read", raise_exception=False)
        )
        lineups_available = bool(
            lineup_model is not None
            and lineup_model.check_access_rights("read", raise_exception=False)
        )
        officials_available = bool(
            official_model is not None
            and official_model.check_access_rights("read", raise_exception=False)
        )
        results_available = bool(
            match_model is not None
            and match_model.check_access_rights("read", raise_exception=False)
        )
        roster_domain = [
            ("season_id", "=", self.season_id.id),
            ("competition_id", "=", self.competition_id.id),
        ]
        roster_action_count = (
            roster_model.search_count(roster_domain + [("ready_for_activation", "=", False)])
            if roster_available else 0
        )
        lineup_action_count = (
            lineup_model.search_count(
                [
                    ("match_id.tournament_id", "in", division_ids),
                    ("state", "in", ("draft", "submitted")),
                ]
            )
            if lineups_available
            else 0
        )
        official_action_count = (
            official_model.search_count([
                ("tournament_id", "in", division_ids),
                ("state", "not in", ("confirmed", "done", "cancelled")),
            ]) if officials_available else 0
        )
        result_action_count = (
            match_model.search_count([
                ("tournament_id", "in", division_ids),
                ("state", "=", "done"),
                ("result_state", "!=", "approved"),
            ]) if results_available else 0
        )
        operation_actions = [
            ("rosters", roster_action_count, _("Complete roster readiness")),
            ("lineups", lineup_action_count, _("Prepare game-day lineups")),
            ("officials", official_action_count, _("Complete official coverage")),
            ("results", result_action_count, _("Complete result follow-up")),
        ]
        if current_issue:
            primary_action = {
                "kind": "issue",
                "key": current_issue["key"],
                "label": current_issue["action_label"],
                "title": current_issue["title"],
                "message": current_issue["message"],
                "owner": current_issue["owner"],
            }
        else:
            pending_operation = next(
                (item for item in operation_actions if item[1]), None
            )
            if pending_operation:
                primary_action = {
                    "kind": "operation",
                    "key": pending_operation[0],
                    "label": pending_operation[2],
                    "title": _("Competition operations need attention"),
                    "message": _(
                        "%(count)s item(s) are waiting in the next operational step.",
                        count=pending_operation[1],
                    ),
                    "owner": _("Competition operations"),
                }
            else:
                primary_action = {
                    "kind": "operation",
                    "key": "matchdays",
                    "label": _("Open match-day operations"),
                    "title": _("Competition is ready"),
                    "message": _("Planning is complete and no operational blocker is projected."),
                    "owner": _("Match-day manager"),
                }
        operational_blockers = sum(item[1] for item in operation_actions)

        return {
            "edition": {
                "id": self.id,
                "name": self.display_name,
                "season": self.season_id.display_name,
                "date_start": self.date_start,
                "date_end": self.date_end,
                "workflow_mode": self.workflow_mode,
            },
            "steps": steps,
            "current_step": current["key"],
            "current_label": current["label"],
            "current_issue": current_issue,
            "complete": all(step["complete"] for step in steps),
            "primary_action": primary_action,
            "readiness": {
                "status": (
                    "blocked"
                    if issues
                    else ("attention" if operational_blockers else "ready")
                ),
                "setup_complete": all(step["complete"] for step in steps),
                "setup_blocker_count": len(issues),
                "operational_action_count": operational_blockers,
                "summary": (
                    _("Resolve the current planning blocker.")
                    if issues
                    else (
                        _("Planning is complete; operational follow-up remains.")
                        if operational_blockers
                        else _("Planning and current operational checks are ready.")
                    )
                ),
            },
            "can_use_advanced_tools": self.env.user.has_group(
                "sports_federation_base.group_federation_advanced_operator"
            ),
            "operations": {
                "next_matchday": {
                    "id": next_matchday.id,
                    "name": next_matchday.display_name,
                    "date": next_matchday.date,
                    "state": next_matchday.state,
                } if next_matchday else False,
                "matchday_count": len(gamedays),
                "schedule_count": len(schedules),
                "roster_action_count": roster_action_count,
                "lineup_action_count": lineup_action_count,
                "official_action_count": official_action_count,
                "result_action_count": result_action_count,
                "rosters_available": roster_available,
                "lineups_available": lineups_available,
                "officials_available": officials_available,
                "results_available": results_available,
            },
            "counts": counts,
            "divisions": division_rows,
            "issues": issues,
        }
