from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from ..journey_navigation import presentation


class OperationTaskJourneys(models.Model):
    _inherit = "federation.operation.task"

    journey_url = fields.Char(compute="_compute_journey_url")

    def _compute_journey_url(self):
        for task in self:
            task.journey_url = ("/odoo/federation.operation.task/%s" % task.id if task.audience == "manager"
                                else "/my/work/tasks/%s/open" % task.id)

    @api.model
    def _sync_specs(self, specs, scope_domain):
        # Existing broad sync does not own the new registration-derived missing-roster task.
        dedicated = ("source_model", "=", "federation.season.registration") in scope_domain
        if not dedicated:
            scope_domain = list(scope_domain) + [("source_model", "!=", "federation.season.registration")]
        keys = {spec["source_key"] for spec in specs}
        existing = self.sudo().search(scope_domain)
        matching = self.sudo().search([("source_key", "in", list(keys))])
        by_key = {task.source_key: task for task in matching}
        for values in specs:
            values = dict(values)
            task = by_key.get(values["source_key"])
            if not task:
                self.sudo().create(values)
                continue
            if task.state == "done":
                values.update(state="open", completed_on=False, digest_sent_on=False)
            changes = {}
            for key, value in values.items():
                current = task[key]
                if task._fields[key].type == "many2one":
                    current = current.id or False
                if current != value:
                    changes[key] = value
            if changes:
                task.sudo().write(changes)
        stale = existing.filtered(lambda task: task.source_key not in keys and task.state != "done")
        if stale:
            stale.sudo().write({"state": "done", "completed_on": fields.Datetime.now()})
        self.invalidate_model(["journey_status", "journey_owner"])

    journey_team_id = fields.Many2one("federation.team", index=True, readonly=True)
    journey_status = fields.Selection([
        ("actionable", "Action needed"), ("waiting", "Waiting for federation"),
        ("completed", "Completed"), ("unavailable", "Source unavailable"),
    ], compute="_compute_journey_presentation")
    journey_owner = fields.Selection([
        ("club", "Club"), ("federation", "Federation"), ("none", "No action needed"),
        ("unknown", "Not checked"),
    ], compute="_compute_journey_presentation")

    @api.model
    def _portal_club_ids(self, user):
        # Effective accounts and current representation, plus explicit team scope.
        reps = self.env["federation.club.representative"].sudo().search([
            ("is_current", "=", True), "|", ("user_id", "=", user.id),
            ("effective_user_id", "=", user.id),
        ])
        return (reps.mapped("club_id") | user.portal_team_scope_ids.mapped("club_id")).ids

    @api.model
    def _portal_get_domain(self, user=None):
        user = user or self.env.user
        clubs = self._portal_club_ids(user)
        # A team-only account must not inherit every task of the team's club.
        full_clubs = set(user.portal_club_scope_ids.ids) & set(clubs)
        return [("audience", "=", "club"), "|",
                ("responsible_club_id", "in", list(full_clubs)),
                ("journey_team_id", "in", user.portal_team_scope_ids.ids)]

    @api.model
    def _journey_waiting_entries(self, user=None):
        user = user or self.env.user
        scope = self.env["federation.match.sheet"]._portal_get_domain(user=user)
        return self.env["federation.portal.privilege"].portal_search(
            self.env["federation.competition.entry"], scope + [("state", "=", "submitted")],
            user=user, order="id desc", limit=100)

    @api.model
    def _task_spec(self, source, *args, **kwargs):
        values = super()._task_spec(source, *args, **kwargs)
        team = source.team_id if "team_id" in source._fields else False
        if source._name == "federation.team.roster.line":
            team = source.roster_id.team_id
        values["journey_team_id"] = team.id if team else False
        if source._name == "federation.competition.entry":
            values["action_url"] = "/my/competition-entries/%s" % source.id
        if source._name == "federation.season.registration":
            values.update(responsible_club_id=source.team_id.club_id.id,
                          season_id=source.season_id.id,
                          action_url="/my/work/registrations/%s" % source.id)
        return values

    @api.model
    def sync_for_user(self, user=None):
        user = user or self.env.user
        super().sync_for_user(user=user)
        # Missing rosters are sourced from confirmed registration, never created by sync.
        roster_model = self.env["federation.team.roster"]
        registrations = roster_model._portal_get_confirmed_registrations(user=user)
        specs = []
        for registration in registrations:
            roster = roster_model._portal_get_primary_roster_for_registration(registration, user=user)
            if not roster:
                specs.append(self._task_spec(
                    registration, "roster_readiness", "club",
                    _("Create roster: %(team)s", team=registration.team_id.display_name),
                    _("This confirmed registration has no roster."),
                    _("Create the roster, add eligible players and activate it.")))
        # Narrow cleanup: do not close other sources or another club's valid task.
        scope = self._portal_get_domain(user) + [
            ("source_model", "=", "federation.season.registration"),
            ("task_type", "=", "roster_readiness"),
        ]
        self._sync_specs(specs, scope)
        return self.sudo().search(self._portal_get_domain(user) + [("state", "!=", "done")])

    @api.depends("state", "audience", "source_model", "source_record_id")
    def _compute_journey_presentation(self):
        # Tasks are scoped by the caller before presentation. Source reads remain projections;
        # no source write, approval or eligibility bypass occurs here.
        grouped = {}
        for task in self:
            grouped.setdefault(task.source_model, set()).add(task.source_record_id)
        sources = {}
        for model, ids in grouped.items():
            if model in self.env:
                sources[model] = {r.id: r for r in self.env[model].sudo().browse(list(ids)).exists()}
        for task in self:
            source = sources.get(task.source_model, {}).get(task.source_record_id)
            source_state = None
            pending = False
            if source:
                source_state = source.state if "state" in source._fields else "present"
                if task.task_type == "parental_consent" and source._name == "federation.team.roster.line":
                    reference = source.roster_id._get_reference_date()
                    pending = bool(source.player_id.parental_approval_ids.filtered(
                        lambda a: a.state == "draft" and a.submitted_on and a.approval_date and a.approval_date <= reference
                        and (not a.valid_until or a.valid_until >= reference)))
            task.journey_status, task.journey_owner = presentation(
                task.state, task.audience, task.source_model, source_state, pending)

    def action_open_source(self):
        self.ensure_one()
        self.check_access("read")
        model = self.env.get(self.source_model)
        source = model.browse(self.source_record_id).exists() if model is not None else False
        if not source:
            raise ValidationError(_("The source was removed. Refresh your workspace."))
        source.check_access("read")
        return super().action_open_source()

    def cron_send_action_digests(self):
        today = fields.Date.context_today(self)
        tasks = self.sudo().search([("state", "!=", "done"), ("assigned_user_id", "!=", False)])
        for user in tasks.mapped("assigned_user_id"):
            self.sync_for_user(user=user)
        self.invalidate_model(["journey_status", "journey_owner"])
        tasks = self.sudo().search([
            ("state", "!=", "done"), ("assigned_user_id", "!=", False),
            "|", ("digest_sent_on", "=", False), ("digest_sent_on", "<", today),
        ]).filtered(lambda task: task.journey_status == "actionable")
        for user in tasks.mapped("assigned_user_id"):
            user_tasks = tasks.filtered(lambda task: task.assigned_user_id == user)
            if not user.has_group("sports_federation_base.group_federation_manager"):
                allowed = self.sudo().search(self._portal_get_domain(user))
                user_tasks &= allowed
            if not user_tasks:
                continue
            first = user_tasks[0]
            first.activity_schedule("mail.mail_activity_data_todo", user_id=user.id,
                                    summary=_("Federation action digest: %(count)s open item(s)", count=len(user_tasks)),
                                    note=_("Open your work inbox for current owners, deadlines and next steps."))
            user_tasks.write({"digest_sent_on": today})
