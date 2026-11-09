from odoo import _, fields, http
from odoo.http import request
from .role_journeys import RoleJourneys, JourneyInbox, JourneyManagerQueue
from .preparation_journey import ClubPreparationJourney
from .officiating import FederationOfficiatingPortal
from odoo.addons.sports_federation_rosters.models.roster_line import (
    _get_parental_approval_reasons,
)
from ..journey_cards import bucket_for, group_cards, participation_status

ROLE_URLS = {
    "club": "/my/preparation",
    "official": "/my/referee-assignments",
    "planner": "/odoo/action-sports_federation_setup_flow.action_competition_setup_home",
    "reviewer": "/my/result-reviews",
    "manager": "/federation/operations/action-items",
}


def task_cards(tasks, representatives=None):
    now = fields.Datetime.now()
    cards = []
    for task in tasks.with_context(journey_viewer_id=request.env.user.id):
        complete = task.state == "done"
        unavailable = task.journey_status == "unavailable"
        waiting = task.journey_status == "waiting" or bool(
            task.assigned_user_id and task.assigned_user_id != request.env.user
        )
        owner = (
            task.assigned_user_id.display_name
            if task.assigned_user_id
            else dict(task._fields["journey_owner"].selection).get(task.journey_owner)
        )
        cards.append(
            {
                "key": "task:%s" % task.id,
                "title": task.name,
                "task": task,
                "representatives": representatives,
                "url": task.journey_url,
                "owner": owner or _("Owner not yet assigned"),
                "event_record": task.match_id,
                "deadline": task.deadline,
                "blocking": task.blocking,
                "blocker": task.blocking_reason or "",
                "next_action": (
                    _("View completed work")
                    if complete
                    else (
                        _("Inspect current status")
                        if unavailable
                        else (
                            _("View submission status")
                            if waiting
                            else task.next_step or _("Open the task to continue")
                        )
                    )
                ),
                "handoff": (
                    _(
                        "This task is complete; source approval and eligibility remain separate checks."
                    )
                    if complete
                    else (
                        _(
                            "The source cannot be checked with your current access. No readiness is implied."
                        )
                        if unavailable
                        else (
                            _(
                                "Your work is handed over. The owner shown is responsible for the next decision."
                            )
                            if waiting
                            else _(
                                "Complete the linked action. Existing approval rules still apply."
                            )
                        )
                    )
                ),
                "bucket": bucket_for(
                    complete=complete,
                    waiting=waiting,
                    unavailable=unavailable,
                    deadline=task.deadline,
                    now=now,
                    blocking=task.blocking,
                ),
            }
        )
    return cards


def review_cards(matches, controller):
    cards = []
    for match in matches:
        complete = match.result_state == "approved"
        actionable = not complete and controller._can_review_match(
            match, request.env.user
        )
        cards.append(
            {
                "key": "result:%s" % match.id,
                "title": match.display_name,
                "url": "/odoo/federation.match/%s" % match.id,
                "owner": (
                    _("No further result decision")
                    if complete
                    else (
                        _("Result validator")
                        if match.result_state == "submitted"
                        else _("Result approver")
                    )
                ),
                "deadline": False,
                "blocker": (
                    _("Independent review requires another authorised reviewer.")
                    if not actionable and not complete
                    else _("No recorded blocker")
                ),
                "next_action": (
                    _("View approved result")
                    if complete
                    else (
                        _("Verify submitted result")
                        if match.result_state == "submitted"
                        else _("Approve verified result")
                    )
                ),
                "handoff": _(
                    "Submission, verification and approval are separate decisions."
                ),
                "bucket": bucket_for(complete=complete, waiting=not actionable),
            }
        )
    return cards


OVERVIEW_CARD_LIMIT = 5


class ConnectedRoleJourneys(RoleJourneys):
    """The portal overview: one page with a section per responsibility.

    Club representatives see their club first. Officials, competition
    planners, result reviewers and federation managers get their own section
    below it, each with the most urgent work and a link to the full list.
    """

    @staticmethod
    def _is_club_representative(user):
        """Match the persona lookup that renders the club overview on /my."""
        return bool(
            request.env["federation.club.representative"]
            .sudo()
            .search_count([("user_id", "=", user.id)], limit=1)
        )

    @http.route()
    def home(self, **kw):
        response = super().home(**kw)
        if getattr(response, "qcontext", None) is not None:
            response.qcontext["federation_overview"] = self._federation_overview()
            response.qcontext["journey_user_id"] = request.env.user.id
        return response

    # ------------------------------------------------------------------
    # Overview data
    # ------------------------------------------------------------------

    def _federation_overview(self):
        user = request.env.user
        overview = {"club": {}, "sections": []}
        if self._is_club_representative(user):
            overview["club"] = self._overview_club(user)
        builders = (
            ("official", self._overview_official),
            ("planner", self._overview_planner),
            ("reviewer", self._overview_reviewer),
            ("manager", self._overview_manager),
        )
        for key, builder in builders:
            section = builder(user)
            if section:
                section["key"] = key
                overview["sections"].append(section)
        return overview

    @staticmethod
    def _overview_section(title, intro, cards, url, url_label):
        groups = group_cards(cards)
        todo = request.env["federation.operation.task"]._journey_actionable_cards(
            groups
        )
        return {
            "title": title,
            "intro": intro,
            "todo": todo[:OVERVIEW_CARD_LIMIT],
            "todo_count": len(todo),
            "waiting_count": len(groups["waiting"]),
            "url": url,
            "url_label": url_label,
        }

    def _overview_club(self, user):
        """Counts and attention badges for the club area tiles."""
        clubs = self._get_portal_clubs()
        club_ids = clubs.ids
        privilege = request.env["federation.portal.privilege"]
        Task = request.env["federation.operation.task"]
        Task.sync_for_user(user=user)
        open_tasks = privilege.portal_search(
            Task,
            Task._portal_get_domain(user) + [("state", "!=", "done")],
            user=user,
        )
        task_counts = {}
        for task in open_tasks:
            task_counts[task.task_type] = task_counts.get(task.task_type, 0) + 1
        roster_model = request.env["federation.team.roster"]
        return {
            "clubs": clubs,
            "teams": privilege.portal_search_count(
                request.env["federation.team"],
                [("club_id", "in", club_ids), ("active", "=", True)],
                user=user,
            ),
            "players": privilege.portal_search_count(
                request.env["federation.player"],
                [("club_id", "in", club_ids), ("active", "=", True)],
                user=user,
            ),
            "rosters": privilege.portal_search_count(
                roster_model,
                roster_model._portal_get_scope_domain(user=user)
                + [("active", "=", True)],
                user=user,
            ),
            "competitions": len(
                request.env[
                    "federation.portal.competition.queries"
                ].visible_editions(user=user)
            ),
            "tasks": len(open_tasks),
            "badges": {
                "teams": task_counts.get("registration", 0),
                "players": task_counts.get("parental_consent", 0),
                "rosters": task_counts.get("roster_readiness", 0),
                "preparation": task_counts.get("gameday_lineup", 0),
                "officials": task_counts.get("referee_duty", 0),
                "results": task_counts.get("result_review", 0),
            },
        }

    def _overview_official(self, user):
        if not request.env["federation.referee"]._portal_get_for_user(user=user):
            return None
        model = request.env["federation.match.referee"]
        live_publications = (
            request.env["federation.matchday"]
            .sudo()
            .search([("current_publication_id.state", "=", "live")])
            .mapped("current_publication_id")
        )
        assignments = request.env["federation.portal.privilege"].portal_search(
            model,
            model._portal_get_domain(user=user)
            + [("publication_id", "in", live_publications.ids)],
            user=user,
            order="id desc",
            limit=100,
        )
        return self._overview_section(
            _("My official assignments"),
            _("Accept or decline assignments before their confirmation deadline."),
            assignment_cards(assignments),
            "/my/referee-assignments",
            _("All my assignments"),
        )

    def _overview_planner(self, user):
        if not user.has_group(
            "sports_federation_competition_core.group_competition_administrator"
        ):
            return None
        cards = []
        now = fields.Datetime.now()
        for edition in request.env["federation.competition.edition"].search(
            [], order="id desc", limit=10
        ):
            data = edition.get_competition_planner_data()
            issue = data.get("current_issue") or {}
            start = (
                fields.Datetime.to_datetime(edition.date_start)
                if edition.date_start
                else False
            )
            cards.append(
                {
                    "key": "edition:%s" % edition.id,
                    "title": edition.display_name,
                    "url": "/odoo/federation.competition.edition/%s" % edition.id,
                    "owner": issue.get("owner") or _("Competition organiser"),
                    "deadline": start,
                    "blocking": bool(issue),
                    "blocker": issue.get("message") or "",
                    "next_action": _("Continue: %s") % data["current_label"],
                    "handoff": _(
                        "The planner resumes at the first incomplete step. "
                        "Publication still requires independent review."
                    ),
                    "bucket": bucket_for(
                        complete=data["complete"],
                        waiting=issue.get("step") == "publication",
                        deadline=start or None,
                        now=now,
                        blocking=bool(issue),
                    ),
                }
            )
        return self._overview_section(
            _("Competition planning"),
            _("Competitions that still need a setup or scheduling step."),
            cards,
            ROLE_URLS["planner"],
            _("Open the competition planner"),
        )

    def _overview_reviewer(self, user):
        states = []
        if user.has_group("sports_federation_result_control.group_result_validator"):
            states.append("submitted")
        if user.has_group("sports_federation_result_control.group_result_approver"):
            states.append("verified")
        if not states:
            return None
        matches = request.env["federation.match"].search(
            [("result_state", "in", states)]
            + request.env["federation.portal.archive.scope"].exclusion_domain(
                "federation.match"
            ),
            order="id desc",
            limit=100,
        )
        return self._overview_section(
            _("Result review"),
            _("Results waiting for your verification or approval."),
            review_cards(matches, self),
            ROLE_URLS["reviewer"],
            _("All results to review"),
        )

    def _overview_manager(self, user):
        if not user.has_group("sports_federation_base.group_federation_manager"):
            return None
        model = request.env["federation.operation.task"]
        model.sync_for_user(user=user)
        tasks = model.search(
            [("audience", "=", "manager"), ("state", "!=", "done")],
            order="blocking desc, deadline asc, id asc",
            limit=200,
        )
        return self._overview_section(
            _("Federation work queue"),
            _("Reviews and follow-up that wait for the federation."),
            task_cards(tasks),
            ROLE_URLS["manager"],
            _("Open the work queue"),
        )

    @http.route()
    def review_work(self, **kw):
        response = super().review_work(**kw)
        if response.status_code == 200 and response.qcontext.get("matches") is not None:
            response.qcontext.update(
                journey_groups=group_cards(
                    review_cards(response.qcontext["matches"], self)
                ),
                journey_user_id=request.env.user.id,
            )
        return response


class ConnectedClubInbox(JourneyInbox):
    @http.route()
    def portal_my_action_items(self, **kw):
        response = super().portal_my_action_items(**kw)
        if response.status_code == 200 and response.qcontext.get("tasks") is not None:
            response.qcontext["journey_groups"] = group_cards(
                task_cards(
                    response.qcontext["tasks"], response.qcontext.get("representatives")
                )
            )
        return response


class ConnectedManagerQueue(JourneyManagerQueue):
    @http.route()
    def manager_action_items(self, **kw):
        response = super().manager_action_items(**kw)
        if response.status_code == 200 and response.qcontext.get("tasks") is not None:
            response.qcontext.update(
                journey_groups=group_cards(
                    task_cards(
                        response.qcontext["tasks"],
                        response.qcontext.get("representatives"),
                    )
                ),
                journey_user_id=request.env.user.id,
            )
        return response


def assignment_cards(assignments):
    cards = []
    for assignment in assignments:
        complete = assignment.state in ("done", "cancelled")
        waiting = assignment.state == "confirmed"
        cards.append(
            {
                "key": "assignment:%s" % assignment.id,
                "title": assignment.match_id.display_name,
                "url": "/my/referee-assignments/%s" % assignment.id,
                "owner": (
                    _("You")
                    if assignment.state == "draft"
                    else _("Match-day organiser")
                ),
                "deadline": assignment.confirmation_deadline,
                "blocker": _("No recorded blocker"),
                "next_action": (
                    _("Accept or decline assignment")
                    if assignment.state == "draft"
                    else _("View assignment status")
                ),
                "handoff": _(
                    "Acceptance is recorded separately from eligibility, attendance and completion."
                ),
                "bucket": bucket_for(
                    complete=complete,
                    waiting=waiting,
                    deadline=assignment.confirmation_deadline,
                    now=fields.Datetime.now(),
                ),
            }
        )
    return cards


class ConnectedOfficialQueue(FederationOfficiatingPortal):
    @http.route()
    def portal_my_referee_assignments(self, **kw):
        response = super().portal_my_referee_assignments(**kw)
        if (
            getattr(response, "qcontext", None)
            and response.qcontext.get("assignments") is not None
        ):
            response.qcontext.update(
                journey_groups=group_cards(
                    assignment_cards(response.qcontext["assignments"])
                ),
                journey_user_id=request.env.user.id,
            )
        return response


class ConnectedPreparation(ClubPreparationJourney):
    @http.route()
    def club_preparation(self, **kw):
        response = super().club_preparation(**kw)
        context = response.qcontext
        if response.status_code != 200 or "rows" not in context:
            return response
        for row in context["rows"]:
            roster = row["roster"]
            checks = [
                dict(
                    label=_("Registration"),
                    state="complete",
                    detail=_("Confirmed registration"),
                    url="/my/season-registrations/%s/roster" % row["registration"].id,
                )
            ]
            roster_issues = roster._get_readiness_issues() if roster else []
            checks.append(
                dict(
                    label=_("Roster"),
                    state="action" if not roster or roster_issues else "complete",
                    detail=(
                        "\n".join(roster_issues)
                        if roster_issues
                        else (
                            _("Create the roster from the existing registration.")
                            if not roster
                            else _(
                                "Current roster checks passed; match-day approval remains separate."
                            )
                        )
                    ),
                    url=(
                        "/my/rosters/%s" % roster.id
                        if roster
                        else "/my/season-registrations/%s/roster" % row["registration"].id
                    ),
                )
            )
            player_issues = (
                [
                    reason
                    for line in roster.line_ids
                    for reason in line._get_eligibility_reasons()
                ]
                if roster
                else []
            )
            checks.append(
                dict(
                    label=_("Player eligibility and licences"),
                    state=(
                        "unknown"
                        if not roster or not roster.line_ids
                        else "action" if player_issues else "complete"
                    ),
                    detail=(
                        "\n".join(player_issues)
                        if player_issues
                        else (
                            _("Current roster-date checks passed.")
                            if roster and roster.line_ids
                            else _("Add players before eligibility can be checked.")
                        )
                    ),
                    url="/my/rosters/%s" % roster.id if roster else "/my/players",
                )
            )
            # Game days come from the team's matches in the registration's
            # season. A line-up sheet exists as soon as a match does, so it must
            # not depend on the roster having been linked to it.
            gameday = request.env["federation.portal.gameday"]
            registration = row["registration"]
            gamedays = gameday.group_gamedays(
                gameday.team_sheets(
                    registration.team_id, registration.season_id, user=request.env.user
                )
            )
            open_gamedays = [item for item in gamedays if item["needs_action"]]
            lineup_state = (
                "not_applicable"
                if not gamedays
                else (
                    "unknown"
                    if not roster
                    else (
                        "action"
                        if open_gamedays
                        else (
                            "waiting"
                            if any(item["state"] == "submitted" for item in gamedays)
                            else "complete"
                        )
                    )
                )
            )
            if not gamedays:
                lineup_detail = _(
                    "No upcoming game days are scheduled yet. Line-ups open when a schedule is published."
                )
            elif not roster:
                lineup_detail = _(
                    "%(count)s upcoming game day(s). Create the roster first, then choose the players for each game day."
                ) % {"count": len(gamedays)}
            elif open_gamedays:
                lineup_detail = _(
                    "%(open)s of %(total)s upcoming game day(s) still need a line-up."
                ) % {"open": len(open_gamedays), "total": len(gamedays)}
            elif lineup_state == "waiting":
                lineup_detail = _("Submitted line-ups await review.")
            else:
                lineup_detail = _("All upcoming line-ups are submitted and approved.")
            checks.append(
                dict(
                    label=_("Game-day line-ups"),
                    state=lineup_state,
                    detail=lineup_detail,
                    url="/my/match-sheets",
                )
            )
            consent_issues = (
                [
                    reason
                    for player in roster.line_ids.mapped("player_id")
                    for reason in _get_parental_approval_reasons(
                        player, roster.team_id, roster._get_reference_date()
                    )
                ]
                if roster
                else []
            )
            checks.append(
                dict(
                    label=_("Parental consent"),
                    state=(
                        "unknown"
                        if not roster or not roster.line_ids
                        else "action" if consent_issues else "complete"
                    ),
                    detail=(
                        "\n".join(consent_issues)
                        if consent_issues
                        else (
                            _(
                                "Current roster-date parental-consent checks passed or are not required."
                            )
                            if roster and roster.line_ids
                            else _(
                                "Add players before consent requirements can be checked."
                            )
                        )
                    ),
                    url="/my/players",
                )
            )
            if roster:
                affected = next(
                    (
                        player
                        for player in roster.line_ids.mapped("player_id")
                        if _get_parental_approval_reasons(
                            player, roster.team_id, roster._get_reference_date()
                        )
                    ),
                    None,
                )
                if affected:
                    checks[-1]["url"] = (
                        "/my/players/%s/parental-approvals" % affected.id
                    )
            from ..context_scope import scoped_url

            for check in checks:
                check["url"] = scoped_url(
                    check["url"],
                    row["registration"].team_id.club_id.id,
                    row["registration"].team_id.id,
                    row["registration"].id,
                )
            row.update(
                participation_checks=checks,
                participation_status=participation_status(checks),
            )
            next_check = next(
                (
                    check
                    for check in checks
                    if check["state"] == "action"
                    and "/parental-approvals" in check["url"]
                ),
                None,
            )
            if not next_check:
                next_check = next(
                    (check for check in checks if check["state"] == "action"), None
                )
            if not next_check:
                next_check = next(
                    (check for check in checks if check["state"] == "unknown"), None
                )
            row["next_check"] = next_check
            row["context_url"] = "/my/preparation?club=%s&team=%s&registration=%s" % (
                row["registration"].team_id.club_id.id,
                row["registration"].team_id.id,
                row["registration"].id,
            )
        context["journey_user_id"] = request.env.user.id
        return response
