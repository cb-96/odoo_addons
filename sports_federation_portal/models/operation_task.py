from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationOperationTask(models.Model):
    """Idempotent operational projections for club and manager follow-up.

    The linked domain record remains authoritative. Tasks only make work
    visible in a shared queue and are regenerated from current source state.
    """

    def _journey_actionable_cards(self, groups):
        from ..journey_cards import actionable_cards

        return actionable_cards(groups)

    _name = "federation.operation.task"
    _description = "Federation Operational Task"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "blocking desc, priority desc, deadline asc, id asc"

    name = fields.Char(required=True, tracking=True)
    task_type = fields.Selection(
        selection=lambda self: self._task_type_selection(),
        required=True,
        index=True,
    )

    @api.model
    def _task_type_selection(self):
        from .. import task_policy

        return task_policy.TASK_TYPE_SELECTION

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
        """Return active representatives in the task's club and optional team scope."""
        self.ensure_one()
        if not self.responsible_club_id:
            return self.env["res.users"].browse()
        domain = [
            ("club_id", "=", self.responsible_club_id.id),
            ("is_current", "=", True),
            ("user_id", "!=", False),
        ]
        if self.journey_team_id:
            domain.append(("team_id", "in", [False, self.journey_team_id.id]))
        reps = self.env["federation.club.representative"].sudo().search(domain)
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

    @api.model
    def action_open_review_queue(self):
        """Open the manager review queue after refreshing the projection.

        Tasks are a projection of source records and are otherwise only
        regenerated when a portal page is loaded, so the backend list would
        show stale work without this refresh.
        """
        if not self.env.user.has_group(
            "sports_federation_base.group_federation_manager"
        ):
            raise ValidationError(_("Federation manager access is required."))
        self.sudo().sync_for_user(user=self.env.user)
        return self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_portal.action_federation_operation_task"
        )

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
        if self.task_type == "parental_consent":
            if source._name == "federation.player":
                return source.action_view_parental_approvals()
            if source._name == "federation.team.roster.line":
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
