from collections import defaultdict

from odoo import _, api, models
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
            return self.get_formview_action()
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
            "target": "current",
            "domain": [("edition_id", "=", self.id)],
            "context": {
                "default_edition_id": self.id,
                "search_default_edition_id": self.id,
                "competition_planner_edition_id": self.id,
            },
        }
        return action

    @api.model
    def _planner_step_label(self, step):
        return {
            "basics": _("Basics"),
            "teams": _("Teams"),
            "format": _("Format"),
            "gamedays": _("Game days"),
            "schedule": _("Schedule"),
            "publication": _("Publish"),
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
            "complete": all(step["complete"] for step in steps),
            "counts": counts,
            "divisions": division_rows,
            "issues": issues,
        }
