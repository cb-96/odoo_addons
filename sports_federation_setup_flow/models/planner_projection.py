from odoo import _, fields, models


class FederationCompetitionEditionPlannerExtension(models.Model):
    _inherit = "federation.competition.edition"

    def get_competition_planner_data(self):
        self.ensure_one()
        self.check_access("read")

        # The planner returns a sanitized readiness projection, not source
        # records. After authorizing the edition, compute that projection with
        # elevated access and edition-scoped queries; keep operation counts and
        # action availability checks below in the caller's original environment.
        projection = self.sudo()
        windows = projection.env["federation.registration.window"].search(
            [("edition_id", "=", self.id)]
        )
        structures = projection.env["federation.competition.structure"].search(
            [("edition_id", "=", self.id)]
        )
        gamedays = projection.env["federation.matchday"].search(
            [("edition_id", "=", self.id)]
        )
        schedules = projection.env["federation.schedule"].search(
            [("edition_id", "=", self.id)]
        )
        (
            division_count,
            participant_count,
            gameday_count,
            schedule_count,
            publication_count,
        ) = projection._setup_counts()
        counts = {
            "divisions": division_count,
            "participants": participant_count,
            "gamedays": gameday_count,
            "schedules": schedule_count,
            "publications": publication_count,
        }
        division_rows, issues, frozen_structures = projection._planner_division_rows(
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
        issues += projection._planner_global_issues(
            gamedays, schedules, expected_fixtures
        )
        issues = projection._planner_enrich_issues(issues)
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
        current = next(
            (step for step in steps if step["status"] == "current"), steps[-1]
        )
        current_issue = next(
            (issue for issue in issues if issue["step"] == current["key"]),
            issues[0] if issues else None,
        )
        next_matchday = gamedays.filtered(
            lambda day: day.state not in ("cancelled", "closed")
        ).sorted(lambda day: (day.date or fields.Date.to_date("9999-12-31"), day.id))[
            :1
        ]
        operation_access = self._usability_operation_access()
        roster_available = operation_access["rosters"]
        lineups_available = operation_access["lineups"]
        officials_available = operation_access["officials"]
        results_available = operation_access["results"]
        tasks = self._usability_pending_tasks()
        roster_action_count = len(tasks["rosters"])
        lineup_action_count = len(tasks["lineups"])
        official_action_count = len(tasks["officials"])
        result_action_count = len(tasks["results"])
        finish_actions = self._planner_finish_actions()
        operation_actions = [
            item for item in finish_actions if item[0] == "publish_website"
        ] + [
            ("results", result_action_count, _("Review completed results")),
            ("rosters", roster_action_count, _("Complete team rosters")),
            ("lineups", lineup_action_count, _("Prepare gameday rosters")),
            ("officials", official_action_count, _("Resolve official coverage")),
        ]
        day_blockers = (
            len(
                gamedays.filtered(
                    lambda d: d.state in ("scheduled", "open")
                    and d.readiness_state != "ready"
                )
            )
            if operation_access["matchdays"]
            else 0
        )
        operation_actions.append(
            ("matchdays", day_blockers, _("Resolve match-day readiness"))
        )
        operation_actions.extend(
            item for item in finish_actions if item[0] != "publish_website"
        )
        unchecked = not all(operation_access.values())
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
            elif self.state == "closed":
                primary_action = {
                    "kind": "operation",
                    "key": "final_tables",
                    "label": _("View final tables"),
                    "title": _("Competition finished"),
                    "message": _(
                        "All results are approved and the final tables are frozen."
                    ),
                    "owner": _("Competition organiser"),
                }
            else:
                primary_action = {
                    "kind": "operation",
                    "key": "matchdays",
                    "label": _("Open match-day operations"),
                    "title": _("Planning is complete"),
                    "message": _(
                        "Open the match day to check readiness. Checks only include records available to your role."
                    ),
                    "owner": _("Match-day manager"),
                }
        operational_blockers = sum(item[1] for item in operation_actions)

        return {
            "edition": {
                "id": self.id,
                "name": self.display_name,
                "season": projection.season_id.display_name,
                "date_start": self.date_start,
                "date_end": self.date_end,
                "workflow_mode": self.workflow_mode,
                "state": self.state,
            },
            "steps": steps,
            "show_setup_progress": not all(step["complete"] for step in steps)
            and not gamedays.filtered(
                lambda day: day.state in ("scheduled", "open", "closed")
            ),
            "remaining_issues": [
                issue
                for issue in issues
                if issue.get("key") != primary_action.get("key")
            ],
            "current_step": current["key"],
            "current_label": current["label"],
            "current_issue": current_issue,
            "complete": all(step["complete"] for step in steps),
            "primary_action": primary_action,
            "readiness": {
                "status": (
                    "blocked"
                    if issues
                    else ("attention" if operational_blockers or unchecked else "ready")
                ),
                "checks_complete": not unchecked,
                "setup_complete": all(step["complete"] for step in steps),
                "setup_blocker_count": len(issues),
                "operational_action_count": operational_blockers,
                "summary": (
                    _("Resolve the current planning blocker.")
                    if issues
                    else (
                        _("Planning is complete; operational follow-up remains.")
                        if operational_blockers
                        else (
                            _("Some operational checks are unavailable to your role.")
                            if unchecked
                            else _("Planning and current operational checks are ready.")
                        )
                    )
                ),
            },
            "can_use_advanced_tools": self.env.user.has_group(
                "sports_federation_base.group_federation_advanced_operator"
            ),
            "operations": {
                "next_matchday": (
                    {
                        "id": next_matchday.id,
                        "name": next_matchday.display_name,
                        "date": next_matchday.date,
                        "state": next_matchday.state,
                    }
                    if next_matchday
                    else False
                ),
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
