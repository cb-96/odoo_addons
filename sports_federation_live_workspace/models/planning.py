"""Canonical visual planning with persisted previews and governed application."""
import json
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError
from ..policy import digest
from .court import _CONTEXT, _TOKEN

CONFIG = {"same_club_weight": "fairness_same_club_weight", "rest_weight": "fairness_rest_weight",
    "consecutive_weight": "fairness_consecutive_weight", "time_balance_weight": "fairness_time_balance_weight",
    "court_balance_weight": "fairness_court_balance_weight", "preferred_rest_minutes": "preferred_rest_minutes",
    "max_consecutive_games": "max_consecutive_games"}


class Constraint(models.Model):
    _name = "federation.visual.constraint"
    _description = "Practical Scheduling Constraint"
    schedule_id = fields.Many2one("federation.schedule", required=True, ondelete="restrict", index=True)
    name = fields.Char(required=True)
    kind = fields.Selection([("team_window", "Team unavailable"), ("court_window", "Court unavailable"),
                             ("minimum_rest", "Hard minimum rest")], required=True)
    team_id = fields.Many2one("federation.team", ondelete="restrict")
    court_id = fields.Many2one("federation.playing.area", ondelete="restrict")
    start = fields.Datetime()
    end = fields.Datetime()
    minutes = fields.Integer(default=0)
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self.env["federation.visual.planning"]._schedule(vals.get("schedule_id"), True)
        return super().create(vals_list)

    def write(self, values):
        for c in self:
            self.env["federation.visual.planning"]._schedule(c.schedule_id.id, True)
        if "schedule_id" in values:
            raise ValidationError(_("Constraints cannot move between schedules."))
        return super().write(values)

    def unlink(self):
        for c in self:
            self.env["federation.visual.planning"]._schedule(c.schedule_id.id, True)
        return super().unlink()

    @api.constrains("kind", "team_id", "court_id", "start", "end", "minutes", "schedule_id")
    def _check(self):
        for c in self:
            if c.kind == "minimum_rest" and not 0 <= c.minutes <= 1440:
                raise ValidationError(_("Rest must be 0 to 1440 minutes."))
            if c.kind != "minimum_rest" and (not c.start or not c.end or c.end <= c.start):
                raise ValidationError(_("Enter a valid unavailable window."))
            if c.kind == "team_window" and c.team_id not in (
                c.schedule_id.available_fixture_ids.mapped("home_team_id") |
                c.schedule_id.available_fixture_ids.mapped("away_team_id")):
                raise ValidationError(_("Choose a team in this schedule."))
            if c.kind == "court_window" and c.court_id not in c.schedule_id.matchday_id.slot_ids.mapped("court_id"):
                raise ValidationError(_("Choose a court in this schedule."))


class Validator(models.AbstractModel):
    _inherit = "federation.schedule.validator"

    def validate_map(self, schedule, assignment_map):
        result = super().validate_map(schedule, assignment_map)
        constraints = self.env["federation.visual.constraint"].sudo().search([
            ("schedule_id", "=", schedule.id), ("active", "=", True)])
        fixtures = {f.id: f for f in schedule.available_fixture_ids}
        slots = {s.id: s for s in schedule.matchday_id.slot_ids}
        windows = {}
        for fid, sid in assignment_map.items():
            fixture, slot = fixtures.get(fid), slots.get(sid)
            if not fixture or not slot:
                continue
            teams = fixture.home_team_id | fixture.away_team_id
            for c in constraints:
                blocked = False
                if ((c.kind == "team_window" and c.team_id in teams) or
                    (c.kind == "court_window" and c.court_id == slot.court_id)):
                    blocked = slot.start_datetime < c.end and c.start < slot.end_datetime
                if c.kind == "minimum_rest":
                    for team in teams:
                        for old in windows.get(team.id, []):
                            gap = max((slot.start_datetime - old.end_datetime).total_seconds(),
                                      (old.start_datetime - slot.end_datetime).total_seconds()) / 60
                            blocked = blocked or gap < c.minutes
                if blocked:
                    result["errors"].append({"code": c.kind, "message": c.name,
                        "fixture_id": fid, "slot_id": sid, "constraint_id": c.id})
            for team in teams:
                windows.setdefault(team.id, []).append(slot)
        result["valid"] = not result["errors"] and not result["unassigned_fixture_ids"]
        return result


class Proposal(models.Model):
    _name = "federation.visual.proposal"
    _description = "Immutable Visual Preview"
    schedule_id = fields.Many2one("federation.schedule", required=True, ondelete="restrict", index=True)
    actor_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    signature = fields.Char(required=True)
    revision = fields.Integer(required=True)
    candidate = fields.Json(required=True)
    methods = fields.Json(required=True)
    comparison = fields.Json(required=True)
    applied = fields.Boolean(default=False)
    applied_reason = fields.Text(readonly=True)
    applied_at = fields.Datetime(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get(_CONTEXT) is not _TOKEN:
            raise AccessError(_("Use the preview command."))
        return super().create(vals_list)

    def write(self, values):
        if self.env.context.get(_CONTEXT) is not _TOKEN or set(values) != {"applied", "applied_reason", "applied_at"}:
            raise AccessError(_("Previews are immutable."))
        return super().write(values)

    @api.ondelete(at_uninstall=False)
    def _retain(self):
        raise ValidationError(_("Previews are retained as evidence."))


class Schedule(models.Model):
    _inherit = "federation.schedule"
    visual_constraint_ids = fields.One2many("federation.visual.constraint", "schedule_id", copy=True)

    def action_visual_plan(self):
        self.ensure_one()
        self.check_access("read")
        return {"type": "ir.actions.client", "tag": "federation_visual_plan",
                "name": _("Visual Planning"), "params": {"schedule_id": self.id}}


class Planning(models.AbstractModel):
    _name = "federation.visual.planning"
    _description = "Explainable Visual Planning"

    def _schedule(self, schedule_id, mutable=False):
        schedule = self.env["federation.schedule"].browse(int(schedule_id or 0)).exists()
        if not schedule:
            raise ValidationError(_("Choose an existing schedule."))
        schedule.check_access("read")
        self.env["federation.competition.role.assignment"].assert_role(schedule.edition_id,
            "schedule_planner", "competition_director", *( [] if mutable else ["schedule_approver"]))
        if mutable:
            schedule.check_access("write")
            schedule.assert_mutable()
        return schedule

    def _map(self, schedule):
        return {a.fixture_id.id: a.slot_id.id for a in schedule.assignment_ids}

    def _cfg(self, schedule):
        return {key: schedule[field] for key, field in CONFIG.items()}

    def _signature(self, schedule):
        return digest({"revision": schedule.revision, "state": schedule.state, "map": self._map(schedule),
            "methods": [(a.fixture_id.id, a.method) for a in schedule.assignment_ids],
            "fixtures": [(f.id, f.state, f.home_team_id.id, f.away_team_id.id, str(f.write_date))
                         for f in schedule.available_fixture_ids],
            "slots": [(s.id, s.state, s.court_id.id, str(s.start_datetime), str(s.end_datetime), str(s.write_date))
                      for s in schedule.matchday_id.slot_ids],
            "blackouts": [(b.id, b.active, str(b.date_start), str(b.date_end), b.playing_area_id.id) for b in schedule.matchday_id.venue_id.blackout_window_ids],
            "constraints": [(c.id, c.active, c.kind, c.team_id.id, c.court_id.id, str(c.start), str(c.end), c.minutes) for c in schedule.visual_constraint_ids],
            "config": self._cfg(schedule)})

    def _explain(self, schedule, candidate):
        validator = self.env["federation.schedule.validator"]
        validation = validator.validate_map(schedule, candidate)
        explanations = []
        for fid in validation["unassigned_fixture_ids"]:
            attempts = []
            for slot in schedule.matchday_id.slot_ids:
                trial = validator.validate_map(schedule, {**candidate, fid: slot.id})
                attempts.append({"slot_id": slot.id, "court": slot.court_id.display_name,
                                 "start": str(slot.start_datetime), "errors": trial["errors"]})
            explanations.append({"fixture_id": fid, "attempts": attempts,
                "message": _("No slots exist. Add court/time capacity.") if not attempts else
                _("Inspect rejected slots. A feasible slot can be pinned manually; heuristic output is not proof of infeasibility.")})
        return {"validation": validation, "unallocated": explanations,
            "fairness": self.env["federation.schedule.fairness.solver"].evaluate(schedule, candidate, self._cfg(schedule))}

    @api.model
    def load(self, schedule_id):
        schedule = self._schedule(schedule_id)
        data = self.env["federation.schedule.queries"].load(schedule.id)
        fixtures = self.env["federation.fixture"].search([("edition_id", "=", schedule.edition_id.id)])
        stages = fixtures.mapped("stage_id") | schedule.structure_id.stage_ids
        data.update({"signature": self._signature(schedule), "explanation": self._explain(schedule, self._map(schedule)),
            "config": self._cfg(schedule), "constraints": [{"id": c.id, "name": c.name, "kind": c.kind,
                "team_id": c.team_id.id, "court_id": c.court_id.id, "start": str(c.start or ""),
                "end": str(c.end or ""), "minutes": c.minutes, "active": c.active} for c in schedule.visual_constraint_ids],
            "fixtures": [{"id": f.id, "name": f.display_name, "stage_id": f.stage_id.id,
                "round": f.round_number, "state": f.state, "home_source": f.home_source_fixture_id.id,
                "away_source": f.away_source_fixture_id.id, "home_outcome": f.home_source_outcome,
                "away_outcome": f.away_source_outcome} for f in fixtures],
            "stages": [{"id": stage.id, "name": stage.name, "format": stage.format_type,
                "state": stage.graph_state, "next": [{"id": p.target_stage_id.id, "rank_from": p.rank_from,
                "rank_to": p.rank_to} for p in stage.outgoing_progression_ids if p.active]} for stage in stages],
            "teams": [{"id": t.id, "name": t.display_name} for t in
                schedule.available_fixture_ids.mapped("home_team_id") | schedule.available_fixture_ids.mapped("away_team_id")],
            "methods": {a.fixture_id.id: a.method for a in schedule.assignment_ids}})
        return data

    @api.model
    def preview(self, schedule_id, operation, fixture_id=False, slot_id=False):
        schedule = self._schedule(schedule_id, True)
        before = self._map(schedule)
        methods = {a.fixture_id.id: a.method for a in schedule.assignment_ids}
        candidate = dict(before)
        if operation == "regenerate":
            proposal = self.env["federation.schedule.fairness.solver"].propose(schedule, replace_automatic=True)
            candidate = {a.fixture_id.id: a.slot_id.id for a in schedule.assignment_ids if a.method != "automatic"}
            for item in proposal["assignments"]:
                candidate[item["fixture_id"]] = item["slot_id"]
                methods[item["fixture_id"]] = "automatic"
        elif operation == "move":
            fid, sid = int(fixture_id), int(slot_id)
            if fid not in schedule.available_fixture_ids.ids or sid not in schedule.matchday_id.slot_ids.ids:
                raise ValidationError(_("Choose a fixture and slot in this schedule."))
            candidate[fid], methods[fid] = sid, "manual"
        elif operation == "unassign":
            candidate.pop(int(fixture_id), None)
        else:
            raise ValidationError(_("Unknown planning operation."))
        comparison = {"before": self._explain(schedule, before), "after": self._explain(schedule, candidate),
            "changes": [{"fixture_id": fid, "old_slot": before.get(fid, False), "new_slot": candidate.get(fid, False)}
                        for fid in sorted(set(before) | set(candidate)) if before.get(fid) != candidate.get(fid)]}
        preview = self.env["federation.visual.proposal"].sudo().with_context(**{_CONTEXT: _TOKEN}).create({
            "schedule_id": schedule.id, "actor_id": self.env.uid, "signature": self._signature(schedule),
            "revision": schedule.revision, "candidate": {str(k): v for k, v in candidate.items()},
            "methods": {str(k): v for k, v in methods.items()}, "comparison": comparison})
        return {"id": preview.id, **comparison}

    @api.model
    def apply(self, preview_id, reason):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise ValidationError(_("Record a bounded reason for this change."))
        with self.env.cr.savepoint():
            preview = self.env["federation.visual.proposal"].sudo().browse(int(preview_id)).exists()
            if not preview or preview.actor_id != self.env.user:
                raise AccessError(_("This preview belongs to another operator."))
            schedule = self._schedule(preview.schedule_id.id, True)
            self.env.cr.execute("SELECT id FROM federation_visual_proposal WHERE id=%s FOR UPDATE", (preview.id,))
            preview.invalidate_recordset()
            if preview.applied:
                if preview.applied_reason != reason.strip():
                    raise ValidationError(_("Applied preview was retried with a different reason."))
                return self.load(schedule.id)
            if preview.signature != self._signature(schedule):
                raise ValidationError(_("Preview is stale. Refresh and compare again."))
            candidate = {int(k): int(v) for k, v in preview.candidate.items()}
            validation = self.env["federation.schedule.validator"].validate_map(schedule, candidate)
            if validation["errors"]:
                raise ValidationError(validation["errors"][0]["message"])
            schedule, revision = self.env["federation.schedule.commands"]._resolve(schedule.id, preview.revision)
            before = self._map(schedule)
            schedule.assignment_ids.filtered(lambda a: candidate.get(a.fixture_id.id) != a.slot_id.id).unlink()
            existing = self._map(schedule)
            for fid, sid in candidate.items():
                if fid not in existing:
                    self.env["federation.schedule.assignment"].create({"schedule_id": schedule.id,
                        "fixture_id": fid, "slot_id": sid, "method": preview.methods.get(str(fid), "manual")})
                elif preview.methods.get(str(fid)) == "manual":
                    schedule.assignment_ids.filtered(lambda a: a.fixture_id.id == fid).write({"method": "manual"})
            for fid in sorted(set(before) | set(candidate)):
                if before.get(fid) != candidate.get(fid):
                    self.env["federation.schedule.change"].create({"schedule_id": schedule.id, "revision": revision,
                        "command": "visual_amend", "fixture_id": fid, "old_slot_id": before.get(fid, False),
                        "new_slot_id": candidate.get(fid, False), "reason": reason.strip(),
                        "idempotency_key": "visual:%s:%s" % (preview.id, fid)})
            preview.with_context(**{_CONTEXT: _TOKEN}).write({"applied": True, "applied_reason": reason.strip(), "applied_at": fields.Datetime.now()})
            return self.load(schedule.id)

    @api.model
    def configure(self, schedule_id, revision, values):
        schedule = self._schedule(schedule_id, True)
        if not isinstance(values, dict) or set(values) - set(CONFIG):
            raise ValidationError(_("Unknown fairness setting."))
        if any(type(v) not in (int, float) or not 0 <= v <= 10000 for v in values.values()):
            raise ValidationError(_("Use finite non-negative bounded fairness settings."))
        with self.env.cr.savepoint():
            schedule, revision = self.env["federation.schedule.commands"]._resolve(schedule.id, revision)
            schedule.write({CONFIG[k]: v for k, v in values.items()})
            self.env["federation.schedule.change"].create({"schedule_id": schedule.id, "revision": revision,
                "command": "visual_constraints", "reason": json.dumps(values, sort_keys=True)})
        return self.load(schedule.id)

    @api.model
    def amend(self, schedule_id, reason):
        schedule = self._schedule(schedule_id)
        replacement = schedule.action_create_revision(reason)
        return {"type": "ir.actions.client", "tag": "federation_visual_plan",
                "params": {"schedule_id": replacement.id}, "name": _("Visual Amendment")}
