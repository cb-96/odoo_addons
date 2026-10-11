from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationOperationTask(models.Model):
    """Idempotent operational projections for club and manager follow-up.

    The linked domain record remains authoritative. Tasks only make work
    visible in a shared queue and are regenerated from current source state.
    """

    _name = "federation.operation.task"
    _description = "Federation Operational Task"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "blocking desc, priority desc, deadline asc, id asc"

    name = fields.Char(required=True, tracking=True)
    task_type = fields.Selection(
        [
            ("registration", "Competition entry"),
            ("roster_readiness", "Roster readiness"),
            ("parental_consent", "Parental consent"),
            ("gameday_lineup", "Game-day lineup"),
            ("referee_duty", "Club referee duty"),
            ("result_review", "Result follow-up"),
        ],
        required=True,
        index=True,
    )
    audience = fields.Selection(
        [("club", "Club"), ("manager", "Tournament manager")],
        required=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("open", "Open"),
            ("acknowledged", "Acknowledged"),
            ("done", "Done"),
        ],
        default="open",
        required=True,
        tracking=True,
        index=True,
    )
    priority = fields.Selection(
        [("0", "Normal"), ("1", "High"), ("2", "Urgent")],
        default="0",
        required=True,
        index=True,
    )
    required_role = fields.Selection(
        [
            ("result_submitter", "Result Submitter"),
            ("result_verifier", "Result Verifier"),
            ("result_approver", "Result Approver"),
            ("competition_manager", "Competition Manager"),
        ],
        string="Required Role",
        index=True,
        readonly=True,
    )
    blocking = fields.Boolean(default=True, index=True)
    blocking_reason = fields.Text()
    next_step = fields.Char()
    action_url = fields.Char(readonly=True)
    deadline = fields.Datetime(index=True)
    is_overdue = fields.Boolean(compute="_compute_is_overdue")
    assigned_user_id = fields.Many2one("res.users", index=True, tracking=True)
    waiting_on = fields.Selection(
        [
            ("club", "Club"),
            ("federation", "Federation"),
            ("external", "External party"),
        ],
        compute="_compute_qol_status",
        store=True,
        index=True,
    )
    work_bucket = fields.Selection(
        [
            ("now", "Needs action now"),
            ("soon", "Due soon"),
            ("waiting", "Waiting"),
            ("recent", "Completed recently"),
        ],
        compute="_compute_qol_status",
        store=True,
        index=True,
    )
    source_changed_on = fields.Datetime(readonly=True)
    digest_sent_on = fields.Date(copy=False, readonly=True)
    responsible_club_id = fields.Many2one(
        "federation.club", index=True, ondelete="cascade"
    )
    season_id = fields.Many2one("federation.season", index=True, ondelete="set null")
    tournament_id = fields.Many2one(
        "federation.tournament", index=True, ondelete="set null"
    )
    match_id = fields.Many2one("federation.match", index=True, ondelete="set null")
    competition_entry_id = fields.Many2one(
        "federation.competition.entry", ondelete="set null"
    )
    roster_id = fields.Many2one("federation.team.roster", ondelete="set null")
    duty_id = fields.Many2one("federation.match.club.referee.duty", ondelete="set null")
    source_model = fields.Char(required=True, index=True, readonly=True)
    source_record_id = fields.Integer(required=True, index=True, readonly=True)
    source_key = fields.Char(required=True, index=True, readonly=True, copy=False)
    completed_on = fields.Datetime(readonly=True)
    escalation_level = fields.Integer(default=0, required=True)

    _source_key_unique = models.Constraint(
        "unique(source_key)", "An operational task source key must be unique."
    )

    @api.model
    def _portal_club_ids(self, user):
        return (
            self.env["federation.club.representative"]
            .sudo()
            .search([("user_id", "=", user.id)])
            .mapped("club_id")
            .ids
        )

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
    def _sync_specs(self, specs, scope_domain):
        keys = {spec["source_key"] for spec in specs}
        existing = self.sudo().search(scope_domain)
        matching = self.sudo().search([("source_key", "in", list(keys))])
        by_key = {task.source_key: task for task in matching}
        for spec in specs:
            task = by_key.get(spec["source_key"])
            if task:
                if task.state == "done":
                    spec.update(state="open", completed_on=False)
                task.sudo().write(spec)
            else:
                self.sudo().create(spec)
        stale = existing.filtered(lambda task: task.source_key not in keys)
        if stale:
            stale.sudo().write({"state": "done", "completed_on": fields.Datetime.now()})

    @api.model
    def sync_for_user(self, user=None):
        """Synchronise currently actionable source records for one user."""
        user = user or self.env.user
        is_manager = user.has_group("sports_federation_base.group_federation_manager")
        club_ids = self._portal_club_ids(user) if not is_manager else []
        if not is_manager and not club_ids:
            return self.browse([])
        specs = []
        entry_domain = [] if is_manager else [("team_id.club_id", "in", club_ids)]
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
                )
            )

        rosters = (
            self.env["federation.team.roster"]
            .sudo()
            .search(
                ([] if is_manager else [("club_id", "in", club_ids)])
                + [("status", "!=", "closed"), ("ready_for_activation", "=", False)]
            )
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
                )
            )

        parental_rosters = (
            self.env["federation.team.roster"]
            .sudo()
            .search(
                ([] if is_manager else [("club_id", "in", club_ids)])
                + [("status", "!=", "closed")]
            )
        )
        roster_lines = parental_rosters.mapped("line_ids").filtered(
            lambda line: line.status == "active"
            and line.roster_id.team_id.category == "senior"
            and line.player_id._is_under_age(
                16, line.roster_id._get_reference_date()
            )
            and not line.player_id._has_verified_parental_approval(
                line.roster_id._get_reference_date()
            )
        )
        for line in roster_lines:
            specs.append(
                self._task_spec(
                    line,
                    "parental_consent",
                    "club",
                    _("Parental consent: %(player)s")
                    % {"player": line.player_id.display_name},
                    _(
                        "A player under 16 in a senior team needs a verified approval covering participation."
                    ),
                    _("Upload and verify parental approval"),
                    priority="2",
                )
            )

        lineup_domain = [] if is_manager else [("team_id.club_id", "in", club_ids)]
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
            lineup_groups.setdefault((sheet.team_id.id, scope), sheet)
        for (team_id, scope), sheet in lineup_groups.items():
            status = (
                _("Submit the shared lineup for this game day.")
                if sheet.state == "draft"
                else _("The shared lineup is waiting for federation approval.")
            )
            spec = self._task_spec(
                sheet,
                "gameday_lineup",
                "club",
                _("Game-day lineup: %(team)s")
                % {"team": sheet.team_id.display_name},
                status,
                _("Prepare game-day lineup"),
                priority="1",
            )
            spec["source_key"] = "gameday-lineup:%s:%s" % (team_id, repr(scope))
            specs.append(spec)

        duties = (
            self.env["federation.match.club.referee.duty"]
            .sudo()
            .search(
                ([] if is_manager else [("club_id", "in", club_ids)])
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
                    "The result is waiting for verification by a Result Verifier."
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
                "submitted": _("Verify result"),
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

        scope_domain = [] if is_manager else [("responsible_club_id", "in", club_ids)]
        scope_domain += [("audience", "=", "manager" if is_manager else "club")]
        self._sync_specs(specs, scope_domain)
        return self.sudo().search(scope_domain + [("state", "!=", "done")])

    @api.model
    def _portal_get_domain(self, user=None):
        user = user or self.env.user
        return [
            ("audience", "=", "club"),
            ("responsible_club_id", "in", self._portal_club_ids(user)),
        ]

    @api.depends("deadline", "state")
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for task in self:
            task.is_overdue = bool(
                task.state != "done" and task.deadline and task.deadline < now
            )

    @api.depends("audience", "state", "deadline", "assigned_user_id", "completed_on")
    def _compute_qol_status(self):
        now = fields.Datetime.now()
        soon = now + timedelta(days=7)
        recent_cutoff = now - timedelta(days=7)
        for task in self:
            task.waiting_on = "club" if task.audience == "club" else "federation"
            if (
                task.state == "done"
                and task.completed_on
                and task.completed_on >= recent_cutoff
            ):
                task.work_bucket = "recent"
            elif task.state == "done":
                task.work_bucket = False
            elif task.deadline and task.deadline <= soon:
                task.work_bucket = "soon" if task.deadline > now else "now"
            else:
                task.work_bucket = "now"

    def _allowed_assignment_users(self):
        """Return active representatives for the task club, never widening club scope."""
        self.ensure_one()
        if not self.responsible_club_id:
            return self.env["res.users"].browse()
        reps = (
            self.env["federation.club.representative"]
            .sudo()
            .search(
                [
                    ("club_id", "=", self.responsible_club_id.id),
                    ("is_current", "=", True),
                    ("user_id", "!=", False),
                ]
            )
        )
        return reps.mapped("effective_user_id") | reps.mapped("user_id")

    def action_assign_user(self, user):
        """Assign within the responsible club or to any internal manager."""
        self.ensure_one()
        user = (
            self.env["res.users"]
            .browse(user.id if hasattr(user, "id") else int(user))
            .exists()
        )
        is_manager_task = self.audience == "manager" and self.env.user.has_group(
            "sports_federation_base.group_federation_manager"
        )
        if not user or (
            not is_manager_task and user not in self._allowed_assignment_users()
        ):
            raise ValidationError(
                _("The selected assignee is not authorized for this club task.")
            )
        self.write({"assigned_user_id": user.id})
        return True

    @api.model
    def cron_send_action_digests(self):
        """Create one actionable daily activity per assignee with open work."""
        today = fields.Date.context_today(self)
        tasks = self.sudo().search(
            [
                ("state", "!=", "done"),
                ("assigned_user_id", "!=", False),
                "|",
                ("digest_sent_on", "=", False),
                ("digest_sent_on", "<", today),
            ]
        )
        for user in tasks.mapped("assigned_user_id"):
            user_tasks = tasks.filtered(lambda task: task.assigned_user_id == user)
            if not user_tasks:
                continue
            first = user_tasks.sorted(
                lambda task: (
                    not task.blocking,
                    task.deadline or fields.Datetime.to_datetime("9999-12-31 00:00:00"),
                )
            )[0]
            first.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=user.id,
                summary=_("Federation action digest: %(count)s open item(s)")
                % {"count": len(user_tasks)},
                note=_(
                    "Open the action inbox to review deadlines, blockers, and direct next steps."
                ),
            )
            user_tasks.write({"digest_sent_on": today})

    def action_open_source(self):
        self.ensure_one()
        source = self.env.get(self.source_model)
        source = (
            source.browse(self.source_record_id).exists()
            if source is not None
            else source
        )
        if not source:
            raise ValidationError(_("The source record no longer exists."))
        if self.task_type == "parental_consent" and source._name == "federation.team.roster.line":
            return source.player_id.action_view_parental_approvals()
        return {
            "type": "ir.actions.act_window",
            "name": source.display_name,
            "res_model": source._name,
            "res_id": source.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_retry_source(self):
        self.ensure_one()
        source = self.env.get(self.source_model)
        source = (
            source.browse(self.source_record_id).exists()
            if source is not None
            else source
        )
        if not source:
            raise ValidationError(_("The source record no longer exists."))
        if source._name != "federation.operation.job" or source.state not in (
            "retry",
            "operator_action",
        ):
            raise ValidationError(
                _("This item must be corrected in its owning workflow.")
            )
        source.action_retry()
        return self.action_open_source()

    def action_acknowledge(self):
        """Acknowledge a warning without pretending the source is resolved."""
        for task in self:
            if task.blocking:
                raise ValidationError(
                    _("Blocking tasks must be resolved in the linked record.")
                )
            if task.state == "open":
                task.write({"state": "acknowledged"})

    def action_escalate(self):
        for task in self:
            task.write({"escalation_level": task.escalation_level + 1, "priority": "2"})
