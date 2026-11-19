from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..planning_fingerprint import fingerprint

_FAIRNESS_FIELDS = (
    "fairness_same_club_weight",
    "fairness_rest_weight",
    "fairness_consecutive_weight",
    "fairness_time_balance_weight",
    "fairness_court_balance_weight",
    "preferred_rest_minutes",
    "max_consecutive_games",
)

_EVIDENCE_FIELDS = {
    "state",
    "proposal",
    "summary",
    "before_snapshot",
    "source_signature",
    "proposal_signature",
    "applied_signature",
    "source_revision",
    "result_revision",
    "prepared_by_id",
    "prepared_on",
    "applied_by_id",
    "applied_on",
    "rolled_back_by_id",
    "rolled_back_on",
}


class FederationSchedulePlanRun(models.Model):
    _name = "federation.schedule.plan.run"
    _description = "Governed Schedule Planning Run"
    _order = "id desc"

    name = fields.Char(required=True, default=lambda self: _("New planning run"))
    schedule_id = fields.Many2one(
        "federation.schedule", required=True, ondelete="cascade", index=True
    )
    plan_type = fields.Selection(
        [("schedule", "Schedule placement")],
        required=True,
        default="schedule",
        index=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("ready", "Ready to apply"),
            ("applied", "Applied"),
            ("rolled_back", "Rolled back"),
        ],
        required=True,
        default="draft",
        readonly=True,
        copy=False,
        index=True,
    )
    configuration = fields.Json(default=dict, copy=False)
    proposal = fields.Json(readonly=True, copy=False)
    summary = fields.Json(readonly=True, copy=False)
    before_snapshot = fields.Json(readonly=True, copy=False)
    source_signature = fields.Char(readonly=True, copy=False, index=True)
    proposal_signature = fields.Char(readonly=True, copy=False)
    applied_signature = fields.Char(readonly=True, copy=False)
    source_revision = fields.Integer(readonly=True, copy=False)
    result_revision = fields.Integer(readonly=True, copy=False)
    prepared_by_id = fields.Many2one(
        "res.users", readonly=True, copy=False, ondelete="set null"
    )
    prepared_on = fields.Datetime(readonly=True, copy=False)
    applied_by_id = fields.Many2one(
        "res.users", readonly=True, copy=False, ondelete="set null"
    )
    applied_on = fields.Datetime(readonly=True, copy=False)
    rolled_back_by_id = fields.Many2one(
        "res.users", readonly=True, copy=False, ondelete="set null"
    )
    rolled_back_on = fields.Datetime(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, values_list):
        if any(_EVIDENCE_FIELDS & set(values) for values in values_list):
            raise UserError(_("Planning evidence is written only by run commands."))
        runs = super().create(values_list)
        for run in runs.filtered(lambda item: item.name == _("New planning run")):
            run.name = f"{run.schedule_id.name} · {run.plan_type}"
        return runs

    def write(self, values):
        if _EVIDENCE_FIELDS & set(values):
            raise UserError(_("Planning evidence is written only by run commands."))
        if {"name", "schedule_id", "plan_type", "configuration"} & set(values):
            if any(run.state != "draft" for run in self):
                raise UserError(_("Prepared planning runs cannot be edited."))
        return super().write(values)

    def _write_evidence(self, values):
        """Bypass the public write guard for this model's command methods."""
        return super().write(values)

    def unlink(self):
        if any(run.state != "draft" for run in self):
            raise UserError(_("Prepared planning evidence cannot be deleted."))
        return super().unlink()

    def _check_schedule_planner(self):
        self.ensure_one()
        self.env["federation.competition.role.assignment"].assert_role(
            self.schedule_id.edition_id, "schedule_planner", "competition_director"
        )
        self.schedule_id.check_access("write")

    def _normalized_schedule_configuration(self):
        self.ensure_one()
        schedule = self.schedule_id
        defaults = {
            "same_club_weight": schedule.fairness_same_club_weight,
            "rest_weight": schedule.fairness_rest_weight,
            "consecutive_weight": schedule.fairness_consecutive_weight,
            "time_balance_weight": schedule.fairness_time_balance_weight,
            "court_balance_weight": schedule.fairness_court_balance_weight,
            "preferred_rest_minutes": schedule.preferred_rest_minutes,
            "max_consecutive_games": schedule.max_consecutive_games,
            "replace_automatic_assignments": False,
        }
        unknown = set(self.configuration or {}) - set(defaults)
        if unknown:
            raise ValidationError(
                _("Unsupported schedule planning options: %s")
                % ", ".join(sorted(unknown))
            )
        defaults.update(self.configuration or {})
        weights = (
            defaults["same_club_weight"],
            defaults["rest_weight"],
            defaults["consecutive_weight"],
            defaults["time_balance_weight"],
            defaults["court_balance_weight"],
        )
        if min(weights) < 0:
            raise ValidationError(_("Fairness weights cannot be negative."))
        if (
            defaults["preferred_rest_minutes"] < 0
            or defaults["max_consecutive_games"] < 1
        ):
            raise ValidationError(
                _("Enter a valid rest target and consecutive-game limit.")
            )
        defaults["replace_automatic_assignments"] = bool(
            defaults["replace_automatic_assignments"]
        )
        return defaults

    def _schedule_solver_configuration(self):
        values = self._normalized_schedule_configuration()
        return {
            key: values[key] for key in values if key != "replace_automatic_assignments"
        }

    def _schedule_input_snapshot(self):
        self.ensure_one()
        schedule = self.schedule_id
        configuration = self._normalized_schedule_configuration()
        fixtures = schedule.matchday_id.allocation_ids.mapped("fixture_ids").sorted(
            "id"
        )
        slots = schedule.matchday_id.slot_ids.sorted("id")
        return {
            "schedule": schedule.id,
            "state": schedule.state,
            "revision": schedule.revision,
            "configuration": configuration,
            "assignments": [
                (item.fixture_id.id, item.slot_id.id, item.method)
                for item in schedule.assignment_ids.sorted("id")
            ],
            "fixtures": [
                (
                    item.id,
                    item.state,
                    item.home_team_id.id,
                    item.away_team_id.id,
                    item.home_source_fixture_id.id,
                    item.away_source_fixture_id.id,
                    item.stage_id.id,
                )
                for item in fixtures
            ],
            "slots": [
                (
                    item.id,
                    item.state,
                    item.start_datetime,
                    item.end_datetime,
                    item.court_id.id,
                )
                for item in slots
            ],
        }

    def _schedule_source_signature(self):
        return fingerprint(self._schedule_input_snapshot())

    def _schedule_proposal(self):
        self.ensure_one()
        values = self._normalized_schedule_configuration()
        return self.env["federation.schedule.fairness.solver"].propose(
            self.schedule_id,
            self._schedule_solver_configuration(),
            values["replace_automatic_assignments"],
        )

    def _schedule_before_snapshot(self):
        schedule = self.schedule_id
        return {
            "assignments": [
                {
                    "fixture_id": item.fixture_id.id,
                    "slot_id": item.slot_id.id,
                    "method": item.method,
                    "assigned_by_id": item.assigned_by_id.id,
                }
                for item in schedule.assignment_ids.sorted("id")
            ],
            "configuration": {field: schedule[field] for field in _FAIRNESS_FIELDS},
            "fairness_last_score": schedule.fairness_last_score,
            "fairness_last_report": schedule.fairness_last_report,
        }

    def _prepare_plan(self):
        self.ensure_one()
        if self.plan_type != "schedule":
            raise ValidationError(_("Unsupported planning run type."))
        self._check_schedule_planner()
        self.schedule_id.assert_mutable()
        proposal = self._schedule_proposal()
        if not proposal["assignments"]:
            raise UserError(_("The schedule solver found no changes to persist."))
        return {
            "configuration": self._normalized_schedule_configuration(),
            "proposal": proposal,
            "summary": {
                "proposed_count": len(proposal["assignments"]),
                "unassigned_count": len(proposal["unassigned_fixture_ids"]),
                "fairness_score": proposal["fairness"]["weighted_score"],
            },
            "before_snapshot": self._schedule_before_snapshot(),
            "source_signature": self._schedule_source_signature(),
            "source_revision": self.schedule_id.revision,
        }

    def action_prepare(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Only a draft planning run can be prepared."))
        values = self._prepare_plan()
        values.update(
            {
                "state": "ready",
                "proposal_signature": fingerprint(values["proposal"]),
                "prepared_by_id": self.env.user.id,
                "prepared_on": fields.Datetime.now(),
            }
        )
        self._write_evidence(values)
        return self._reopen()

    def _apply_plan(self):
        self.ensure_one()
        if self.plan_type != "schedule":
            raise ValidationError(_("Unsupported planning run type."))
        self._check_schedule_planner()
        self.schedule_id.assert_mutable()
        if self.source_revision != self.schedule_id.revision:
            raise UserError(_("The schedule changed after this run was prepared."))
        if self.source_signature != self._schedule_source_signature():
            raise UserError(_("Schedule inputs changed. Prepare a new planning run."))
        current = self._schedule_proposal()
        if self.proposal_signature != fingerprint(current):
            raise UserError(_("The solver result changed. Prepare a new planning run."))
        values = self._normalized_schedule_configuration()
        wizard = self.env["federation.schedule.auto.wizard"].create(
            {
                "schedule_id": self.schedule_id.id,
                "same_club_weight": values["same_club_weight"],
                "rest_weight": values["rest_weight"],
                "consecutive_weight": values["consecutive_weight"],
                "time_balance_weight": values["time_balance_weight"],
                "court_balance_weight": values["court_balance_weight"],
                "preferred_rest_minutes": values["preferred_rest_minutes"],
                "max_consecutive_games": values["max_consecutive_games"],
                "replace_automatic_assignments": values[
                    "replace_automatic_assignments"
                ],
            }
        )
        wizard.action_apply()
        self.schedule_id.invalidate_recordset(["revision", "assignment_ids"])
        return {
            "result_revision": self.schedule_id.revision,
            "applied_signature": self._schedule_source_signature(),
        }

    def action_apply(self):
        self.ensure_one()
        if self.state != "ready":
            raise UserError(_("Only a prepared planning run can be applied."))
        result = self._apply_plan()
        result.update(
            {
                "state": "applied",
                "applied_by_id": self.env.user.id,
                "applied_on": fields.Datetime.now(),
            }
        )
        self._write_evidence(result)
        return self._reopen()

    def _rollback_plan(self):
        self.ensure_one()
        if self.plan_type != "schedule":
            raise ValidationError(_("Unsupported planning run type."))
        self._check_schedule_planner()
        schedule = self.schedule_id
        schedule.assert_mutable()
        if self.result_revision != schedule.revision:
            raise UserError(_("The schedule changed after this run was applied."))
        if self.applied_signature != self._schedule_source_signature():
            raise UserError(
                _("Schedule inputs changed; this run cannot be rolled back.")
            )
        schedule, new_revision = self.env["federation.schedule.commands"]._resolve(
            schedule.id, self.result_revision
        )
        schedule.assignment_ids.unlink()
        assignments = self.before_snapshot.get("assignments", [])
        if assignments:
            self.env["federation.schedule.assignment"].create(
                [dict(item, schedule_id=schedule.id) for item in assignments]
            )
        restore = dict(self.before_snapshot.get("configuration", {}))
        restore.update(
            {
                "fairness_last_score": self.before_snapshot.get("fairness_last_score"),
                "fairness_last_report": self.before_snapshot.get(
                    "fairness_last_report"
                ),
            }
        )
        schedule.write(restore)
        self.env["federation.schedule.change"].create(
            {
                "schedule_id": schedule.id,
                "revision": new_revision,
                "command": "planning_run_rollback",
                "reason": _("Rolled back planning run %s") % self.display_name,
            }
        )
        schedule.invalidate_recordset(["revision", "assignment_ids"])
        return {"result_revision": new_revision}

    def action_rollback(self):
        self.ensure_one()
        if self.state != "applied":
            raise UserError(_("Only an applied planning run can be rolled back."))
        result = self._rollback_plan()
        result.update(
            {
                "state": "rolled_back",
                "rolled_back_by_id": self.env.user.id,
                "rolled_back_on": fields.Datetime.now(),
            }
        )
        self._write_evidence(result)
        return self._reopen()

    def _reopen(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Planning Run"),
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "current",
        }


class FederationSchedulePlanningRuns(models.Model):
    _inherit = "federation.schedule"

    planning_run_ids = fields.One2many(
        "federation.schedule.plan.run",
        "schedule_id",
        string="Planning Runs",
        copy=False,
    )
    planning_run_count = fields.Integer(compute="_compute_planning_run_count")

    @api.depends("planning_run_ids")
    def _compute_planning_run_count(self):
        for schedule in self:
            schedule.planning_run_count = len(schedule.planning_run_ids)

    def action_create_schedule_plan_run(self):
        self.ensure_one()
        run = self.env["federation.schedule.plan.run"].create(
            {"schedule_id": self.id, "plan_type": "schedule"}
        )
        return run.action_prepare()

    def action_open_planning_runs(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Planning Runs"),
            "res_model": "federation.schedule.plan.run",
            "view_mode": "list,form",
            "domain": [("schedule_id", "=", self.id)],
            "context": {"default_schedule_id": self.id},
        }
