"""Govern reviewed club-duty planning end to end.

* The active planning policy of the schedule's season provides the review
  defaults and the governed-run configuration. Its id and version join the
  review fingerprint, so changing the active policy requires a new review
  before publication.
* A policy may choose the exact optimizer. It refines the local-search balance
  with OR-Tools CP-SAT when installed and is kept only when it scores better.
* Every blocking allocation issue carries concrete suggested fixes.
* Duties added to a current published schedule are recorded in a live
  allocation run. It can be rolled back while the publication is unchanged and
  every duty it created is still open and unnominated.
* Schedules show their planning runs and live allocations.
"""

from html import escape

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from ..duty_allocation import fingerprint
from ..duty_exact_solver import solve_season
from ..duty_explanations import attach_suggestions
from ..duty_season_balance import role_minutes

MANAGER_GROUP = "sports_federation_base.group_federation_manager"
LIVE_RUN_COMMAND = "club_duty_live_run_command"
LIVE_RUN_PROTECTED = {"state", "rolled_back_by_id", "rolled_back_on"}


class FederationClubDutyLiveRun(models.Model):
    _name = "federation.club.duty.live.run"
    _description = "Club-Duty Allocation Applied to a Published Schedule"
    _order = "id desc"
    _rec_name = "schedule_id"

    schedule_id = fields.Many2one(
        "federation.schedule",
        required=True,
        readonly=True,
        index=True,
        ondelete="cascade",
    )
    matchday_id = fields.Many2one(
        related="schedule_id.matchday_id", store=True, index=True
    )
    publication_ref = fields.Integer(string="Publication", readonly=True)
    policy_id = fields.Many2one(
        "federation.club.duty.policy",
        string="Planning policy",
        readonly=True,
        ondelete="set null",
    )
    policy_version = fields.Integer(readonly=True)
    duty_ids = fields.Many2many(
        "federation.match.club.referee.duty",
        "federation_club_duty_live_run_duty_rel",
        "run_id",
        "duty_id",
        string="Created duties",
        readonly=True,
    )
    applied_duty_count = fields.Integer(readonly=True)
    duty_count = fields.Integer(compute="_compute_duty_count")
    proposal = fields.Json(readonly=True)
    state = fields.Selection(
        [("applied", "Applied"), ("rolled_back", "Rolled back")],
        default="applied",
        required=True,
        readonly=True,
    )
    applied_by_id = fields.Many2one(
        "res.users", readonly=True, default=lambda self: self.env.user
    )
    applied_on = fields.Datetime(readonly=True, default=fields.Datetime.now)
    rolled_back_by_id = fields.Many2one("res.users", readonly=True)
    rolled_back_on = fields.Datetime(readonly=True)
    rollback_blockers = fields.Text(compute="_compute_rollback_blockers")

    @api.depends("duty_ids")
    def _compute_duty_count(self):
        for run in self:
            run.duty_count = len(run.duty_ids)

    def _rollback_blocker_list(self):
        self.ensure_one()
        if self.state != "applied":
            return [_("This allocation was already rolled back.")]
        problems = []
        if len(self.duty_ids) != self.applied_duty_count:
            problems.append(_("Some duties of this allocation were already removed."))
        publication = self.schedule_id.matchday_id.current_publication_id
        if not publication or publication.id != self.publication_ref:
            problems.append(
                _(
                    "The match day was republished after this allocation. Review "
                    "the current publication instead."
                )
            )
        for duty in self.duty_ids:
            if duty.state != "open":
                problems.append(
                    _("%(duty)s is no longer open.") % {"duty": duty.display_name}
                )
            elif duty.nominated_player_id:
                problems.append(
                    _("%(duty)s already has a nomination.")
                    % {"duty": duty.display_name}
                )
        return problems

    @api.depends(
        "state", "applied_duty_count", "duty_ids.state", "duty_ids.nominated_player_id"
    )
    def _compute_rollback_blockers(self):
        for run in self:
            if run.state == "applied":
                run.rollback_blockers = "\n".join(run._rollback_blocker_list())
            else:
                run.rollback_blockers = False

    def write(self, values):
        if LIVE_RUN_PROTECTED & values.keys() and not self.env.context.get(
            LIVE_RUN_COMMAND
        ):
            raise UserError(_("Use Roll back to change an applied allocation."))
        return super().write(values)

    def action_rollback(self):
        self.ensure_one()
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(
                _("Only federation managers may roll back club-duty allocations.")
            )
        problems = self._rollback_blocker_list()
        if problems:
            raise UserError("\n".join(problems))
        duties = self.duty_ids
        dispatcher = self.env.get("federation.notification.dispatcher")
        if dispatcher is not None and hasattr(dispatcher, "send_club_duty_withdrawn"):
            for duty in duties:
                dispatcher.send_club_duty_withdrawn(duty)
        duties.unlink()
        self.with_context(**{LIVE_RUN_COMMAND: True}).write(
            {
                "state": "rolled_back",
                "rolled_back_by_id": self.env.user.id,
                "rolled_back_on": fields.Datetime.now(),
            }
        )
        return True


class FederationScheduleGovernedClubDuties(models.Model):
    _inherit = "federation.schedule"

    club_duty_plan_run_ids = fields.One2many(
        "federation.schedule.plan.run",
        "schedule_id",
        string="Planning runs",
        readonly=True,
    )
    club_duty_live_run_ids = fields.One2many(
        "federation.club.duty.live.run",
        "schedule_id",
        string="Live club-duty allocations",
        readonly=True,
    )

    def _club_duty_active_policy(self):
        self.ensure_one()
        return self.env["federation.club.duty.policy"]._active_for_season(
            self.edition_id.season_id
        )

    def _club_duty_policy_reference(self):
        policy = self._club_duty_active_policy()
        if not policy:
            return {}
        return {
            "id": policy.id,
            "version": policy.version,
            "name": policy.name,
            "solver": policy.solver,
        }

    def _duty_fingerprint(self, policy):
        signature = super()._duty_fingerprint(policy)
        reference = self._club_duty_policy_reference()
        if not reference:
            return signature
        return fingerprint({"allocation": signature, "planning_policy": reference})

    def _duty_proposal(self, policy):
        proposal = super()._duty_proposal(policy)
        proposal["planning_policy"] = self._club_duty_policy_reference() or False
        return attach_suggestions(proposal, policy)

    def _club_duty_fairness_rebalance(self, allocation, policy=None):
        allocation = super()._club_duty_fairness_rebalance(allocation, policy)
        fairness = allocation.get("fairness")
        if not fairness or not fairness.get("engaged"):
            return allocation
        fairness.setdefault("solver", "local_search")
        planning_policy = self._club_duty_active_policy()
        if planning_policy.solver != "exact":
            return allocation
        options = policy or self.club_duty_policy or {}
        heuristic = allocation["rows"]
        rows, report = solve_season(
            heuristic,
            self._duty_geometry(),
            capacities=self._club_duty_capacity_policy(),
            avoid_playing=bool(options.get("avoid", True)),
            allow_fallback=bool(options.get("fallback", False)),
            season_minutes=self._club_duty_season_load(),
            targets=self._club_duty_target_minutes(),
            fixed_rows=allocation.get("preserved") or [],
            effort=planning_policy.solver_effort,
        )
        if report.get("solver") != "exact":
            fairness["solver_note"] = report.get("solver_status")
            if report.get("proven_optimal"):
                fairness["proven_optimal"] = True
            return allocation
        load = dict(allocation.get("load") or {})
        minute_load = dict(allocation.get("minute_load") or {})
        for old, new in zip(heuristic, rows):
            if old["club"] == new["club"]:
                continue
            source, target = str(old["club"]), str(new["club"])
            for totals, amount in (
                (load, len(old["roles"])),
                (minute_load, role_minutes(old)),
            ):
                totals[source] = totals.get(source, 0) - amount
                totals[target] = totals.get(target, 0) + amount
        report["objective_before"] = fairness.get("objective_before")
        report["fallback_before"] = fairness.get("fallback_before")
        allocation.update(
            rows=rows, load=load, minute_load=minute_load, fairness=report
        )
        return allocation

    def action_create_club_duty_plan_run(self):
        self.ensure_one()
        policy = self._club_duty_active_policy()
        if not policy:
            return super().action_create_club_duty_plan_run()
        run = self.env["federation.schedule.plan.run"].create(
            {
                "schedule_id": self.id,
                "plan_type": "club_duty",
                "configuration": policy.review_options(),
            }
        )
        return run.action_prepare()


class ClubDutyReviewGovernance(models.TransientModel):
    _inherit = "federation.schedule.club.duty.review"

    @api.model
    def _schedule_ids_from_commands(self, commands):
        ids = []
        for command in commands or []:
            if not isinstance(command, (list, tuple)) or not command:
                continue
            if command[0] == fields.Command.SET:
                ids = list(command[2])
            elif command[0] == fields.Command.LINK:
                ids.append(command[1])
        return ids

    @api.model_create_multi
    def create(self, values_list):
        Policy = self.env["federation.club.duty.policy"]
        for values in values_list:
            schedules = self.env["federation.schedule"].browse(
                self._schedule_ids_from_commands(values.get("schedule_ids"))
            )
            policies = Policy.browse()
            for schedule in schedules:
                policies |= Policy._active_for_season(schedule.edition_id.season_id)
            if len(policies) == 1:
                for key, value in policies.review_options().items():
                    values.setdefault(key, value)
        return super().create(values_list)

    def _suggestion_text(self, code):
        texts = {
            "resolve_participants": _(
                "Resolve both participating teams of the fixture."
            ),
            "change_pin": _("Change or remove the pin on this fixture."),
            "raise_capacity": _(
                "Raise a club's simultaneous capacity on its capacity policy."
            ),
            "shorten_buffers": _(
                "Shorten preparation, rest or travel buffers on the capacity policy."
            ),
            "qualify_roles": _(
                "Qualify more clubs for the required roles on their capacity "
                "policies."
            ),
            "allow_fallback": _("Allow playing-club fallback for this review."),
            "move_fixture": _("Move the fixture to a slot where more clubs are free."),
            "assign_referee": _(
                "Assign a federation referee to the missing roles instead."
            ),
            "resolve_existing": _(
                "Resolve or replace the conflicting existing duty, then refresh "
                "the preview."
            ),
        }
        return texts.get(code, code)

    def _solver_text(self, fairness):
        if not fairness.get("engaged"):
            return ""
        if fairness.get("solver") == "exact":
            if fairness.get("proven_optimal"):
                return _(
                    "Balanced with the exact optimizer; the plan is proven optimal."
                )
            return _("Balanced with the exact optimizer within its effort budget.")
        notes = {
            "exact_unavailable": _(
                "Balanced with local search: OR-Tools is not installed on this server."
            ),
            "no_improvement": _(
                "Balanced with local search; the exact optimizer found no better plan."
            ),
        }
        note = notes.get(fairness.get("solver_note"))
        if note and fairness.get("proven_optimal"):
            note += " " + _("The plan is proven optimal.")
        return note or _("Balanced with local search.")

    def _governance_html(self, schedule, proposal):
        parts = []
        reference = proposal.get("planning_policy")
        if reference:
            parts.append(
                "<p>%s</p>"
                % escape(
                    _("Planning policy: %(name)s v%(version)s")
                    % {"name": reference["name"], "version": reference["version"]}
                )
            )
        solver_text = self._solver_text(proposal.get("fairness") or {})
        if solver_text:
            parts.append("<p>%s</p>" % escape(solver_text))
        items = []
        for detail in proposal.get("issue_details") or []:
            codes = detail.get("suggestions") or []
            if not codes:
                continue
            fixes = "".join(
                "<li>%s</li>" % escape(self._suggestion_text(code)) for code in codes
            )
            items.append(
                "<li>%s<ul>%s</ul></li>"
                % (escape(str(detail.get("message") or "")), fixes)
            )
        if items:
            title = _("Suggested fixes: %s") % schedule.display_name
            parts.append("<h5>%s</h5><ul>%s</ul>" % (escape(title), "".join(items)))
        return "".join(parts)

    def action_preview(self):
        action = super().action_preview()
        sections = [
            self._governance_html(
                schedule, (self.preview or {}).get(str(schedule.id)) or {}
            )
            for schedule in self.schedule_ids
        ]
        sections = [section for section in sections if section]
        if sections:
            html = str(self.preview_html or "") + "".join(sections)
            self.write({"preview_html": html})
        return action

    def _apply_live_duties(self, schedule, proposal):
        Duty = self.env["federation.match.club.referee.duty"]
        match_ids = sorted({row["match"] for row in proposal["rows"]})
        before = set(Duty.search([("match_id", "in", match_ids)]).ids)
        result = super()._apply_live_duties(schedule, proposal)
        created = Duty.search(
            [("match_id", "in", match_ids), ("id", "not in", list(before))]
        )
        if created:
            policy = schedule._club_duty_active_policy()
            publication = schedule.matchday_id.current_publication_id
            self.env["federation.club.duty.live.run"].create(
                {
                    "schedule_id": schedule.id,
                    "publication_ref": publication.id,
                    "policy_id": policy.id,
                    "policy_version": policy.version,
                    "duty_ids": [fields.Command.set(created.ids)],
                    "applied_duty_count": len(created),
                    "proposal": proposal,
                }
            )
        return result


class FederationClubDutyPlanRunGovernance(models.Model):
    _inherit = "federation.schedule.plan.run"

    def _prepare_plan(self):
        values = super()._prepare_plan()
        if len(self) != 1 or self.plan_type != "club_duty":
            return values
        reference = ((values or {}).get("proposal") or {}).get("planning_policy")
        if reference:
            values["summary"] = dict(
                values.get("summary") or {}, planning_policy=reference
            )
        return values
