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
            )
            team_count = len(participant_sets.mapped("line_ids.team_id"))
            division_structures = structures_by_division[division.id]
            frozen_structures = division_structures.filtered(lambda item: item.state == "frozen")

            teams_status = "complete" if participant_sets else "attention"
            format_status = "complete" if frozen_structures else "blocked"
            if not participant_sets:
                issues.append(
                    {
                        "key": "division-%s-teams" % division.id,
                        "step": "teams",
                        "severity": "blocking",
                        "title": division.display_name,
                        "message": _("Finalize the participating teams for this division."),
                    }
                )
            elif not division_structures:
                issues.append(
                    {
                        "key": "division-%s-format" % division.id,
                        "step": "format",
                        "severity": "blocking",
                        "title": division.display_name,
                        "message": _("Choose and generate a competition format."),
                    }
                )
            elif not frozen_structures:
                issues.append(
                    {
                        "key": "division-%s-freeze" % division.id,
                        "step": "format",
                        "severity": "blocking",
                        "title": division.display_name,
                        "message": _("Review and freeze the generated format."),
                    }
                )

            rows.append(
                {
                    "id": division.id,
                    "name": division.display_name,
                    "team_count": team_count,
                    "teams_status": teams_status,
                    "format_status": format_status,
                    "format_name": frozen_structures[:1].display_name or False,
                    "ready": bool(participant_sets and frozen_structures),
                }
            )
        return rows, issues

    def _planner_global_issues(self, counts, gamedays, schedules):
        issues = []
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

        if counts["participants"] and not counts["gamedays"]:
            issues.append(
                {
                    "key": "missing-gamedays",
                    "step": "gamedays",
                    "severity": "blocking",
                    "title": _("Game-day plan"),
                    "message": _("Create at least one game day and define its court capacity."),
                }
            )
        if counts["gamedays"] and not counts["schedules"]:
            issues.append(
                {
                    "key": "missing-schedule",
                    "step": "schedule",
                    "severity": "blocking",
                    "title": _("Schedule"),
                    "message": _("Generate a working schedule from the frozen formats."),
                }
            )
        if counts["schedules"] and not counts["publications"]:
            issues.append(
                {
                    "key": "missing-publication",
                    "step": "publication",
                    "severity": "blocking",
                    "title": _("Publication"),
                    "message": _("Complete review and publish the approved schedule."),
                }
            )

        for gameday in gamedays.filtered(lambda item: item.spare_capacity < 0):
            issues.append(
                {
                    "key": "gameday-%s-capacity" % gameday.id,
                    "step": "gamedays",
                    "severity": "blocking",
                    "title": gameday.display_name,
                    "message": _("Add playable court capacity or reduce allocated fixtures."),
                }
            )

        if "unassigned_fixture_count" in schedules._fields:
            for schedule in schedules.filtered("unassigned_fixture_count"):
                issues.append(
                    {
                        "key": "schedule-%s-unassigned" % schedule.id,
                        "step": "schedule",
                        "severity": "blocking",
                        "title": schedule.display_name,
                        "message": _("Assign every fixture before review."),
                    }
                )
        return issues

    def _planner_steps(self, counts, division_rows, issues):
        divisions_ready = bool(counts["divisions"])
        teams_ready = divisions_ready and all(
            row["teams_status"] == "complete" for row in division_rows
        )
        formats_ready = teams_ready and all(
            row["format_status"] == "complete" for row in division_rows
        )
        completion = {
            "basics": divisions_ready,
            "teams": teams_ready,
            "format": formats_ready,
            "gamedays": bool(counts["gamedays"]),
            "schedule": bool(counts["schedules"]),
            "publication": bool(counts["publications"]),
        }
        issue_counts = defaultdict(int)
        for issue in issues:
            issue_counts[issue["step"]] += 1
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
        division_rows, issues = self._planner_division_rows(windows, structures)
        issues += self._planner_global_issues(counts, gamedays, schedules)
        steps = self._planner_steps(counts, division_rows, issues)
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
