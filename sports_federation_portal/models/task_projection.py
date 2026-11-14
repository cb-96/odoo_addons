from datetime import datetime, time, timedelta
from time import monotonic

from odoo import _, api, fields, models
from odoo.fields import Domain

from odoo.addons.sports_federation_base.batch_jobs import in_test_mode

from .. import task_policy


class FederationOperationTaskExtension(models.Model):
    _inherit = "federation.operation.task"

    @api.model
    def _portal_club_ids(self, user):
        return (
            self.env["federation.club.representative"]
            .sudo()
            .search([("user_id", "=", user.id)])
            .mapped("club_id")
            .ids
        )

    ROSTER_DEADLINE_DAYS = 7

    @api.model
    def _prefetch_roster_deadlines(self, cache, keys):
        """Fill ``cache`` with the roster deadline of each (team, season, competition).

        The deadline is the date from which matches of the team can no longer be
        scheduled or finished without an active, ready roster: seven days before
        the team's first match in the season (or the tournament start when no
        match is scheduled yet), exactly as the match roster-deadline rule
        computes it. Tasks that depend on the roster carry it as their deadline,
        so clubs see it, the work inbox sorts by it and the due-soon reminder
        covers it. A key is ``(team_id, season_id, competition_id or 0)``; its
        value is ``False`` when the team has no tournament in that season yet.
        All keys are resolved with a fixed number of queries because the work
        inbox is refreshed on every page load.
        """
        keys = {key for key in keys if key[0] and key[1]} - set(cache)
        if not keys:
            return cache
        team_ids = {key[0] for key in keys}
        season_ids = {key[1] for key in keys}
        tournaments = (
            self.env["federation.tournament"]
            .sudo()
            .search(
                [
                    "|",
                    ("season_id", "in", list(season_ids)),
                    "&",
                    ("season_id", "=", False),
                    ("edition_id.season_id", "in", list(season_ids)),
                ]
            )
        )
        season_of = {
            tournament.id: (tournament.season_id or tournament.edition_id.season_id).id
            for tournament in tournaments
        }
        # Teams take part in a tournament through a participant record or a match.
        involved = set()
        for participant in (
            self.env["federation.tournament.participant"]
            .sudo()
            .search(
                [
                    ("team_id", "in", list(team_ids)),
                    ("tournament_id", "in", tournaments.ids),
                    ("state", "!=", "withdrawn"),
                ]
            )
        ):
            involved.add((participant.team_id.id, participant.tournament_id.id))
        first_match = {}
        matches = (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    ("tournament_id", "in", tournaments.ids),
                    ("state", "!=", "cancelled"),
                    "|",
                    ("home_team_id", "in", list(team_ids)),
                    ("away_team_id", "in", list(team_ids)),
                ],
                order="date_scheduled asc, id asc",
            )
        )
        for match in matches:
            for team in match.home_team_id | match.away_team_id:
                if team.id not in team_ids:
                    continue
                involved.add((team.id, match.tournament_id.id))
                if match.date_scheduled:
                    first_match.setdefault(
                        (team.id, match.tournament_id.id),
                        fields.Datetime.to_datetime(match.date_scheduled).date(),
                    )
        by_team = {}
        for team_id, tournament_id in involved:
            by_team.setdefault(team_id, []).append(tournaments.browse(tournament_id))
        for team_id, season_id, competition_id in keys:
            days = []
            for tournament in by_team.get(team_id, []):
                if season_of.get(tournament.id) != season_id:
                    continue
                if competition_id and tournament.competition_id.id != competition_id:
                    continue
                day = first_match.get((team_id, tournament.id)) or tournament.date_start
                if day:
                    days.append(day)
            cache[(team_id, season_id, competition_id)] = (
                datetime.combine(
                    min(days) - timedelta(days=self.ROSTER_DEADLINE_DAYS), time.min
                )
                if days
                else False
            )
        return cache

    @api.model
    def _roster_deadline(self, team, season, competition=None, cache=None):
        """Return the roster deadline of one team in one season (see above)."""
        if not team or not season:
            return False
        key = (team.id, season.id, competition.id if competition else 0)
        if cache is None:
            cache = {}
        if key not in cache:
            self._prefetch_roster_deadlines(cache, [key])
        return cache[key]

    @staticmethod
    def _roster_deadline_keys(rosters):
        return [
            (roster.team_id.id, roster.season_id.id, roster.competition_id.id or 0)
            for roster in rosters
        ]

    @api.model
    def _task_spec(
        self,
        source,
        task_type,
        audience,
        name,
        reason,
        next_step,
        *,
        priority="0",
        blocking=True,
        deadline=False,
        required_role=False,
    ):
        values = {
            "name": name,
            "task_type": task_type,
            "audience": audience,
            "priority": priority,
            "blocking": blocking,
            "blocking_reason": reason,
            "next_step": next_step,
            "deadline": deadline,
            "required_role": required_role,
            "source_model": source._name,
            "source_record_id": source.id,
            "source_changed_on": source.write_date,
            "source_key": "%s:%s:%s" % (source._name, source.id, task_type),
        }
        if source._name == "federation.competition.entry":
            values.update(
                competition_entry_id=source.id,
                responsible_club_id=source.team_id.club_id.id,
                season_id=source.edition_id.season_id.id,
                tournament_id=source.window_id.division_id.id,
                action_url="/my/competition-entries",
            )
        elif source._name == "federation.team.roster":
            values.update(
                roster_id=source.id,
                responsible_club_id=source.club_id.id,
                season_id=source.season_id.id,
                action_url="/my/rosters/%s" % source.id,
            )
        elif source._name == "federation.team.roster.line":
            roster = source.roster_id
            values.update(
                responsible_club_id=roster.club_id.id,
                season_id=roster.season_id.id,
                roster_id=roster.id,
                action_url=(
                    "/my/players/%s/parental-approvals" % source.player_id.id
                    if task_type == "parental_consent"
                    else "/my/rosters/%s" % roster.id
                ),
            )
        elif source._name == "federation.player":
            values.update(
                responsible_club_id=source.club_id.id,
                action_url="/my/players/%s/parental-approvals" % source.id,
            )
        elif source._name == "federation.match.sheet":
            match = source.match_id
            values.update(
                responsible_club_id=source.team_id.club_id.id,
                season_id=match.tournament_id.season_id.id,
                tournament_id=match.tournament_id.id,
                match_id=match.id,
                roster_id=source.roster_id.id,
                action_url="/my/match-sheets/%s" % source.id,
            )
        elif source._name == "federation.match.club.referee.duty":
            values.update(
                duty_id=source.id,
                responsible_club_id=source.club_id.id,
                tournament_id=source.match_id.tournament_id.id,
                match_id=source.match_id.id,
                season_id=source.match_id.tournament_id.season_id.id,
                action_url="/my/referee-duties/%s" % source.id,
            )
        elif source._name == "federation.match":
            values.update(
                match_id=source.id,
                tournament_id=source.tournament_id.id,
                season_id=source.tournament_id.season_id.id,
                responsible_club_id=(
                    source.home_team_id.club_id.id or source.away_team_id.club_id.id
                ),
                action_url="/my/results/%s" % source.id,
            )
        return values

    @api.model
    def _task_team_scope(self, user, team_field="team_id"):
        """Restrict sources and cleanup to effective whole-club or team scope."""
        if user.has_group("sports_federation_base.group_federation_manager"):
            return []
        clubs = set(self._portal_club_ids(user)) & set(user.portal_club_scope_ids.ids)
        return [
            "|",
            (team_field + ".club_id", "in", sorted(clubs)),
            (team_field, "in", user.portal_team_scope_ids.ids),
        ]

    @api.model
    def _collect_domain_task_specs(self, user=None):
        """Return domain specifications and cleanup scope without writing records."""
        user = user or self.env.user
        is_manager = user.has_group("sports_federation_base.group_federation_manager")
        club_ids = self._portal_club_ids(user) if not is_manager else []
        if not is_manager and not club_ids:
            return [], [("id", "=", 0)]
        specs = []
        # Archived competitions produce no work: their sources are skipped,
        # so their existing tasks fall out of the specs and are closed below.
        hidden = self.env["federation.portal.archive.scope"].exclusion_domain
        entry_domain = self._task_team_scope(user)
        entry_domain += hidden("federation.competition.entry")
        entries = (
            self.env["federation.competition.entry"]
            .sudo()
            .search(
                entry_domain + [("state", "in", ("draft", "submitted", "rejected"))]
            )
        )
        for entry in entries:
            audience = "manager" if entry.state == "submitted" else "club"
            specs.append(
                self._task_spec(
                    entry,
                    "registration",
                    audience,
                    _("Competition entry for %(team)s")
                    % {"team": entry.team_id.display_name},
                    _("Entry is %(state)s and needs follow-up.")
                    % {"state": entry.state},
                    (
                        _("Review competition entry")
                        if entry.state == "submitted"
                        else _("Correct and submit competition entry")
                    ),
                    priority="1" if entry.state == "rejected" else "0",
                    deadline=entry.window_id.date_close or False,
                )
            )

        rosters = (
            self.env["federation.team.roster"]
            .sudo()
            .search(
                self._task_team_scope(user)
                + [("status", "!=", "closed"), ("ready_for_activation", "=", False)]
            )
        )
        deadline_cache = {}
        self._prefetch_roster_deadlines(
            deadline_cache, self._roster_deadline_keys(rosters)
        )
        for roster in rosters:
            specs.append(
                self._task_spec(
                    roster,
                    "roster_readiness",
                    "club",
                    _("Roster readiness: %(team)s")
                    % {"team": roster.team_id.display_name},
                    roster.readiness_feedback
                    or _("The roster is not ready for activation."),
                    _("Complete roster readiness"),
                    deadline=self._roster_deadline(
                        roster.team_id,
                        roster.season_id,
                        roster.competition_id,
                        deadline_cache,
                    ),
                )
            )

        parental_rosters = (
            self.env["federation.team.roster"]
            .sudo()
            .search(self._task_team_scope(user) + [("status", "!=", "closed")])
        )
        roster_lines = parental_rosters.mapped("line_ids").filtered(
            lambda line: line.status == "active"
            and line.roster_id.team_id.category == "senior"
            and line.player_id._is_under_age(16, line.roster_id._get_reference_date())
            and not line.player_id._has_verified_parental_approval(
                line.roster_id._get_reference_date()
            )
        )
        self._prefetch_roster_deadlines(
            deadline_cache, self._roster_deadline_keys(roster_lines.mapped("roster_id"))
        )
        # One task per player: a player on two senior rosters needs one approval,
        # so the club gets one action, due at the earliest roster deadline.
        lines_by_player = {}
        for line in roster_lines:
            lines_by_player.setdefault(line.player_id, []).append(line)
        for player, lines in lines_by_player.items():
            dated = [
                (
                    self._roster_deadline(
                        line.roster_id.team_id,
                        line.roster_id.season_id,
                        line.roster_id.competition_id,
                        deadline_cache,
                    ),
                    line,
                )
                for line in lines
            ]
            deadline, first_line = min(
                dated,
                key=lambda item: (not item[0], item[0] or datetime.max, item[1].id),
            )
            spec = self._task_spec(
                player,
                "parental_consent",
                "club",
                _("Parental consent: %(player)s") % {"player": player.display_name},
                _(
                    "A player under 16 in a senior team needs a verified approval covering participation."
                ),
                _("Upload and verify parental approval"),
                priority="2",
                deadline=deadline,
            )
            roster = first_line.roster_id
            spec.update(
                responsible_club_id=roster.club_id.id,
                season_id=roster.season_id.id,
                roster_id=roster.id,
                journey_team_id=roster.team_id.id,
            )
            specs.append(spec)

        lineup_domain = self._task_team_scope(user)
        lineup_domain += hidden("federation.match.sheet")
        sheets = (
            self.env["federation.match.sheet"]
            .sudo()
            .search(
                lineup_domain
                + [
                    ("state", "in", ("draft", "submitted")),
                    ("match_id.state", "!=", "cancelled"),
                ],
                order="match_kickoff asc,id asc",
            )
        )
        lineup_groups = {}
        for sheet in sheets:
            scope = sheet._get_gameday_scope()
            if not scope and sheet.match_kickoff and sheet.match_id.tournament_id:
                scope = (
                    "tournament_date",
                    sheet.match_id.tournament_id.id,
                    fields.Datetime.to_datetime(sheet.match_kickoff).date(),
                )
            scope = scope or ("sheet", sheet.id)
            key = (sheet.team_id.id, scope)
            current = lineup_groups.get(key)
            if not current or (current.state == "submitted" and sheet.state == "draft"):
                lineup_groups[key] = sheet
        for (team_id, scope), sheet in lineup_groups.items():
            task_type, audience = task_policy.lineup_task(sheet.state)
            reviewing = audience == "manager"
            spec = self._task_spec(
                sheet,
                task_type,
                audience,
                (
                    _("Review game-day line-up: %(team)s")
                    if reviewing
                    else _("Game-day lineup: %(team)s")
                )
                % {"team": sheet.team_id.display_name},
                (
                    _("The game-day line-up was submitted and needs approval.")
                    if reviewing
                    else _("Submit the shared lineup for this game day.")
                ),
                (
                    _("Approve or return the line-up")
                    if reviewing
                    else _("Prepare game-day lineup")
                ),
                priority="1",
                deadline=sheet.match_kickoff or False,
            )
            spec["source_key"] = "gameday-lineup:%s:%s" % (team_id, repr(scope))
            specs.append(spec)

        duties = (
            self.env["federation.match.club.referee.duty"]
            .sudo()
            .search(
                (
                    []
                    if is_manager
                    else [("club_id", "in", club_ids)]
                    + list(
                        Domain.OR(
                            [
                                self._task_team_scope(user, "match_id.home_team_id"),
                                self._task_team_scope(user, "match_id.away_team_id"),
                            ]
                        )
                    )
                )
                + hidden("federation.match.club.referee.duty")
                + [("state", "in", ("open", "rejected"))]
            )
        )
        for duty in duties:
            overdue = duty.is_deadline_overdue
            specs.append(
                self._task_spec(
                    duty,
                    "referee_duty",
                    "club",
                    _("Official needed for %(match)s")
                    % {"match": duty.match_id.display_name},
                    (
                        _("Nominate a club official.")
                        if not overdue
                        else _("The nomination deadline has passed.")
                    ),
                    _("Nominate a club official"),
                    priority="2" if overdue else "1",
                    deadline=duty.nomination_deadline,
                )
            )

        match_domain = (
            []
            if is_manager
            else [
                "|",
                ("home_team_id.club_id", "in", club_ids),
                ("away_team_id.club_id", "in", club_ids),
            ]
        )
        matches = (
            self.env["federation.match"]
            .sudo()
            .search(
                match_domain
                + hidden("federation.match")
                + [
                    (
                        "result_state",
                        "in",
                        ("submitted", "verified", "contested", "corrected"),
                    )
                ]
            )
        )
        for match in matches:
            reason_by_state = {
                "submitted": _(
                    "The result is waiting for approval by the tournament manager."
                ),
                "verified": _(
                    "The result is waiting for approval by a Result Approver."
                ),
                "contested": _(
                    "The result is contested and must return to the submitter for correction."
                ),
                "corrected": _(
                    "The corrected result must be submitted again by a Result Submitter."
                ),
            }
            next_step_by_state = {
                "submitted": _("Approve result"),
                "verified": _("Approve result"),
                "contested": _("Correct contested result"),
                "corrected": _("Submit corrected result"),
            }
            role_by_state = {
                "submitted": "result_verifier",
                "verified": "result_approver",
                "contested": "result_submitter",
                "corrected": "result_submitter",
            }
            specs.append(
                self._task_spec(
                    match,
                    "result_review",
                    "manager",
                    _("Result follow-up: %(match)s") % {"match": match.display_name},
                    reason_by_state[match.result_state],
                    next_step_by_state[match.result_state],
                    priority="2" if match.result_state == "contested" else "1",
                    required_role=role_by_state[match.result_state],
                    deadline=(
                        fields.Datetime.to_datetime(match.date_scheduled)
                        + timedelta(days=1)
                        if match.date_scheduled
                        else False
                    ),
                )
            )

        scope_domain = (
            [("audience", "=", "manager")]
            if is_manager
            else self._portal_get_domain(user)
        )
        # A handoff changes audience on the same key. Include both audiences
        # for line-ups so approval/locking also closes existing reviewer work.
        lineup_scope = [("task_type", "in", ("gameday_lineup", "lineup_review"))]
        if not is_manager:
            lineup_scope += self._task_team_scope(user, "journey_team_id")
        return specs, list(Domain.OR([scope_domain, lineup_scope]))

    @api.model
    def _task_projection_collectors(self):
        """Owning addons extend this list with read-only collectors via super()."""
        return ("_collect_domain_task_specs",)

    @api.model
    def _project_task_specs(self, user=None):
        """Collect all specifications before the synchronization service writes."""
        user = user or self.env.user
        specs, scopes = [], []
        for name in self._task_projection_collectors():
            collected, scope = getattr(self, name)(user=user)
            specs.extend(collected)
            scopes.append(scope)
        return specs, list(Domain.OR(scopes)) if scopes else [("id", "=", 0)]

    @api.model
    def sync_for_user(self, user=None):
        """Bring the user's tasks up to date before a page shows them.

        Rebuilding the projection reads every domain in scope and writes the
        task rows, so page views share it instead of each paying for it:

        - once per HTTP request, however many page parts ask for it;
        - for page views (HTTP GET), a projection younger than
          ``task_projection_max_age`` seconds (system parameter
          ``sports_federation_portal.task_projection_max_age``, default 30;
          0 disables) is reused. Any portal change by the user discards it,
          so their own actions always show at once;
        - while another transaction is rebuilding the same clubs, this one
          shows the current tasks instead of writing the same rows (which
          would only end in a serialization retry).

        Outside HTTP requests (tests, scheduled jobs, commands) it always
        rebuilds.
        """
        user = user or self.env.user
        freshness = _ProjectionFreshness(self.env, user)
        if freshness.can_reuse():
            return self._current_tasks_for(user)
        if not freshness.try_lock():
            return self._current_tasks_for(user)
        result = self.env["federation.task.projection"].synchronize(user=user)
        freshness.mark_synced()
        return result

    @api.model
    def _current_tasks_for(self, user):
        return self.sudo().search(
            self._portal_get_domain(user) + [("state", "!=", "done")]
        )

    @api.model
    def _forget_projection_for(self, user):
        """Make the next page view of ``user`` rebuild their tasks."""
        _ProjectionFreshness.forget(self.env, user)


# Process-local freshness of task projections: {(database, user id): monotonic
# time of the last rebuild}. Each worker keeps its own; a stale entry only means
# one extra rebuild.
_LAST_SYNC = {}
_LAST_SYNC_LIMIT = 10000
# Namespace of the transaction-level advisory locks taken per club while a
# projection is rebuilt (two-integer form: namespace, club id).
_LOCK_NAMESPACE = 731_406
_MANAGER_SCOPE = 0


class _ProjectionFreshness:
    """Decides whether a page view may reuse the user's last task projection."""

    def __init__(self, env, user):
        self.env = env
        self.user = user
        self.key = (env.cr.dbname, user.id)
        self.http_request = _current_http_request(env)

    @classmethod
    def forget(cls, env, user):
        for one in user:
            _LAST_SYNC.pop((env.cr.dbname, one.id), None)
        request = _current_http_request(env)
        if request is not None:
            getattr(request, "_sf_task_synced_users", set()).difference_update(user.ids)

    def max_age(self):
        default = "0" if in_test_mode(self.env) else "30"
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("sports_federation_portal.task_projection_max_age", default)
        )
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 30

    def can_reuse(self):
        if self.http_request is None:
            return False
        synced = getattr(self.http_request, "_sf_task_synced_users", set())
        if self.user.id in synced:
            return True
        if self.http_request.httprequest.method != "GET":
            return False
        age = self.max_age()
        last = _LAST_SYNC.get(self.key)
        return bool(age and last is not None and monotonic() - last < age)

    def try_lock(self):
        """Lock the clubs of this projection; False when another rebuild holds one."""
        user = self.user.sudo()
        club_ids = set()
        for name in ("portal_club_scope_ids", "portal_team_scope_ids"):
            if name in user._fields:
                records = user[name]
                club_ids |= set(
                    records.ids
                    if records._name == "federation.club"
                    else records.club_id.ids
                )
        if not club_ids:
            club_ids = {_MANAGER_SCOPE}
        for club_id in sorted(club_ids):
            self.env.cr.execute(
                "SELECT pg_try_advisory_xact_lock(%s, %s)", (_LOCK_NAMESPACE, club_id)
            )
            if not self.env.cr.fetchone()[0]:
                return False
        return True

    def mark_synced(self):
        if self.http_request is None:
            return
        synced = getattr(self.http_request, "_sf_task_synced_users", None)
        if synced is None:
            synced = set()
            try:
                self.http_request._sf_task_synced_users = synced
            except AttributeError:  # request objects without a __dict__
                pass
        synced.add(self.user.id)
        if len(_LAST_SYNC) >= _LAST_SYNC_LIMIT:
            _LAST_SYNC.clear()
        _LAST_SYNC[self.key] = monotonic()


def _current_http_request(env):
    """The HTTP request that runs on this cursor, or None."""
    try:
        from odoo.http import request
    except ImportError:  # pragma: no cover - always importable in Odoo
        return None
    if not request:
        return None
    try:
        if request.env.cr is not env.cr:
            return None
    except (AttributeError, RuntimeError):
        return None
    return request
