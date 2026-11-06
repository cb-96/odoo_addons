"""Read-only readiness and issue projection for the competition planner."""
from collections import defaultdict

from odoo import _, api, models


class FederationCompetitionPlannerReadiness(models.Model):
    _inherit = "federation.competition.edition"

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
            "teams": _("Set up teams & format"),
            "format": _("Set up teams & format"),
            "gamedays": _("Define game days"),
            "schedule": _("Plan competition"),
            "publication": (
                _("Submit schedule for review")
                if self.schedule_approval_required
                else _("Publish schedule")
            ),
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
                        "message": _("Select the teams for this division."),
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
                        "message": _("Choose how this division plays."),
                    }
                )
            elif current_structure.state == "draft" and current_structure.format_type == "custom":
                issues.append(
                    {
                        "key": "division-%s-stages" % division.id,
                        "step": "format",
                        "severity": "blocking",
                        "title": division.display_name,
                        "message": _(
                            "Finish the stages of this division in the stage builder "
                            "and choose Generate all matches."
                        ),
                    }
                )
            elif current_structure.state != "frozen":
                issues.append(
                    {
                        "key": "division-%s-freeze" % division.id,
                        "step": "format",
                        "severity": "blocking",
                        "title": division.display_name,
                        "message": _("Confirm the format of this division."),
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
                        "message": _("This format produces no matches. Check the teams and format."),
                    }
                )

            rows.append(
                {
                    "id": division.id,
                    "name": division.display_name,
                    "team_count": team_count,
                    "teams_status": teams_status,
                    "format_status": format_status,
                    "format_name": (
                        _("Custom stages (not generated yet)")
                        if current_structure.format_type == "custom"
                        and current_structure.state != "frozen"
                        else current_structure.display_name or False
                    ),
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
                    "title": _("Match allocation"),
                    "message": _(
                        "Plan all %(count)s matches on game days.",
                        count=len(unallocated_fixtures),
                    ),
                }
            )

        active_days = gamedays.filtered(lambda item: item.state != "cancelled")
        if active_days and "division_ids" in active_days._fields:
            for division in expected_fixtures.mapped("division_id").sorted(
                lambda item: (item.name or "", item.id)
            ):
                if not any(day._allows_division(division) for day in active_days):
                    issues.append(
                        {
                            "key": "nogameday-%s-division" % division.id,
                            "step": "gamedays",
                            "severity": "blocking",
                            "title": division.display_name,
                            "message": _(
                                "No game day lets this division play. Add it to the "
                                "divisions playing of at least one game day."
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
                            "Move this division's matches to an active game day."
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
                            "Add courts or time, or move matches to another game day."
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
                        "message": _("Complete the courts and times of this game day."),
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
                            "Publish this game day's schedule."
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
                            "Publish the latest schedule changes for this game day."
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
                    "message": _("Plan the matches on at least one game day."),
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
