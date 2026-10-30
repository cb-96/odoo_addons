"""Scoped court capture with immutable receipts and optimistic concurrency."""
import json
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError
from odoo.addons.sports_federation_result_control.services.result_commands import (
    _RESULT_COMMAND_CONTEXT_KEY, _RESULT_COMMAND_TOKEN,
)
from ..policy import digest, validate_capture, validate_command

_TOKEN = object()
_CONTEXT = "live_workspace_token"


class CourtAccess(models.Model):
    _name = "federation.court.access"
    _description = "Named Court Operator"
    matchday_id = fields.Many2one("federation.matchday", required=True, ondelete="restrict", index=True)
    court_id = fields.Many2one("federation.playing.area", required=True, ondelete="restrict", index=True)
    user_id = fields.Many2one("res.users", required=True, ondelete="restrict", index=True)
    active = fields.Boolean(default=True)
    _unique = models.Constraint("unique(matchday_id,court_id,user_id)", "Operator already assigned.")

    @api.constrains("court_id", "matchday_id", "user_id")
    def _check_scope(self):
        for item in self:
            if item.court_id.venue_id != item.matchday_id.venue_id or item.user_id.share:
                raise ValidationError(_("Assign an internal operator to a court at this venue."))

    def _assert_manager(self):
        if not self.env.user.has_group("sports_federation_matchday.group_matchday_manager"):
            raise AccessError(_("Only match-day managers assign court operators."))

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_manager()
        for vals in vals_list:
            day = self.env["federation.matchday"].browse(vals.get("matchday_id")).exists()
            if not day:
                raise ValidationError(_("Choose an existing match day."))
            self.env["federation.competition.role.assignment"].assert_role(
                day.edition_id, "matchday_manager", "competition_director")
        return super().create(vals_list)

    def write(self, values):
        self._assert_manager()
        if {"matchday_id", "court_id", "user_id"}.intersection(values):
            raise ValidationError(_("Deactivate the old operator assignment and create a new one to preserve history."))
        for item in self:
            self.env["federation.competition.role.assignment"].assert_role(
                item.matchday_id.edition_id, "matchday_manager", "competition_director")
        return super().write(values)

    def unlink(self):
        self._assert_manager()
        raise ValidationError(_("Deactivate court operator assignments; retain their history."))


class CourtCapture(models.Model):
    _name = "federation.court.capture"
    _description = "Server Court Result Draft"
    match_id = fields.Many2one("federation.match", required=True, ondelete="restrict", index=True)
    revision = fields.Integer(default=0, required=True)
    payload = fields.Json(default=dict, required=True)
    previous_payload = fields.Json(default=dict)
    undo_available = fields.Boolean(default=False)
    submitted = fields.Boolean(default=False)
    review_required = fields.Boolean(default=False)
    closed = fields.Boolean(default=False)
    signature = fields.Char(required=True)
    _unique = models.Constraint("unique(match_id)", "One server capture per match.")

    @api.model_create_multi
    def create(self, vals_list):
        self._assert_command()
        return super().create(vals_list)

    def action_resolve_exception(self):
        self.ensure_one()
        self.check_access("read")
        return {"type": "ir.actions.act_window", "res_model": "federation.court.resolve.wizard",
                "views": [(False, "form")], "target": "new", "context": {
                    "default_capture_id": self.id, "default_expected_revision": self.revision}}

    def action_open_result(self):
        self.ensure_one()
        self.check_access("read")
        self.match_id.check_access("read")
        return {"type": "ir.actions.act_window", "res_model": "federation.match",
                "res_id": self.match_id.id, "views": [(False, "form")], "target": "current"}

    def _assert_command(self):
        if self.env.context.get(_CONTEXT) is not _TOKEN:
            raise AccessError(_("Use the scoped court command service."))

    def write(self, values):
        self._assert_command()
        return super().write(values)

    @api.ondelete(at_uninstall=False)
    def _retain(self):
        raise ValidationError(_("Court captures are retained as result evidence."))


class CourtReceipt(models.Model):
    _name = "federation.court.receipt"
    _description = "Immutable Court Command Receipt"
    _order = "id desc"
    capture_id = fields.Many2one("federation.court.capture", required=True, ondelete="restrict", index=True)
    key = fields.Char(required=True, index=True)
    digest = fields.Char(required=True)
    actor_id = fields.Many2one("res.users", required=True, ondelete="restrict")
    operation = fields.Char(required=True)
    response = fields.Json(required=True)
    _unique = models.Constraint("unique(capture_id,key)", "Command already processed.")

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get(_CONTEXT) is not _TOKEN:
            raise AccessError(_("Court receipts are command-owned."))
        return super().create(vals_list)

    def write(self, values):
        raise ValidationError(_("Court receipts are immutable."))

    @api.ondelete(at_uninstall=False)
    def _retain(self):
        raise ValidationError(_("Court receipts are retained."))


class LiveEdition(models.Model):
    _inherit = "federation.competition.edition"
    court_scoring_mode = fields.Selection([
        ("aggregate", "Aggregate"), ("periods", "Period totals"), ("sets", "Sets won")
    ], default="aggregate", required=True)
    court_set_target = fields.Integer(default=0)
    court_max_periods = fields.Integer(default=100)

    @api.constrains("court_set_target", "court_max_periods")
    def _check_scoring_config(self):
        for item in self:
            if not 0 <= item.court_set_target <= 100 or not 1 <= item.court_max_periods <= 100:
                raise ValidationError(_("Use a bounded set target and 1 to 100 periods."))


class LiveMatch(models.Model):
    _inherit = "federation.match"
    court_outcome = fields.Selection([(k, v) for k, v in [
        ("normal", "Normal"), ("interrupted", "Interrupted"), ("abandoned", "Abandoned"),
        ("forfeit_home", "Home forfeits"), ("forfeit_away", "Away forfeits"), ("disputed", "Disputed")
    ]], default="normal", readonly=True)
    court_outcome_reason = fields.Text(readonly=True)

    def write(self, values):
        if {"court_outcome", "court_outcome_reason"}.intersection(values) and self.env.context.get(_CONTEXT) is not _TOKEN:
            raise AccessError(_("Exceptional court outcomes require an audited command."))
        return super().write(values)


class CourtCommands(models.AbstractModel):
    _name = "federation.court.commands"
    _description = "Run This Court Commands"

    def _access(self, matchday_id, court_id):
        actor = self.env.user
        if actor.share:
            raise AccessError(_("Court operation requires a named internal account."))
        access = self.env["federation.court.access"].sudo().search([
            ("matchday_id", "=", int(matchday_id)), ("court_id", "=", int(court_id)),
            ("user_id", "=", actor.id), ("active", "=", True)
        ], limit=1)
        if not access:
            raise AccessError(_("You are not assigned to this court."))
        session = access.matchday_id.active_session_id
        if not session or session.state != "open":
            raise ValidationError(_("Open the published match-day session before running this court."))
        self.env.cr.execute("SELECT id FROM federation_court_access WHERE id=%s FOR SHARE", (access.id,))
        access.invalidate_recordset()
        if not access.active or access.user_id != actor:
            raise AccessError(_("Court access was revoked."))
        self.env.cr.execute("SELECT id FROM federation_matchday_session WHERE id=%s FOR SHARE", (session.id,))
        session.invalidate_recordset()
        if session.state != "open" or session.publication_id != access.matchday_id.current_publication_id:
            raise ValidationError(_("The operational publication changed. Reopen the current session."))
        return access, session

    def _match(self, access, match_id):
        match = self.env["federation.match"].sudo().browse(int(match_id)).exists()
        if not match or match.schedule_publication_id.matchday_id != access.matchday_id:
            raise AccessError(_("Match is outside this court."))
        slot = match.operational_slot_id or match.published_slot_id
        if not slot or slot.court_id != access.court_id or match.operational_status in {"cancelled", "postponed"}:
            raise AccessError(_("Match is not currently runnable on this court."))
        return match

    def _signature(self, match, session):
        slot = match.operational_slot_id or match.published_slot_id
        return digest({"publication": session.publication_digest, "session": session.id,
                       "slot": slot.id, "start": str(slot.start_datetime), "end": str(slot.end_datetime),
                       "deviations": match.operational_deviation_ids.ids, "operational_state": match.operational_status,
                       "home": match.home_score, "away": match.away_score, "state": match.result_state,
                       "teams": [match.home_team_id.id, match.away_team_id.id],
                       "scoring": [match._competition_workflow_edition().court_scoring_mode,
                                   match._competition_workflow_edition().court_set_target],
                       "periods": [(p.sequence, p.home_score, p.away_score) for p in match.result_period_ids]})

    def _capture(self, match, signature):
        Capture = self.env["federation.court.capture"].sudo().with_context(**{_CONTEXT: _TOKEN})
        capture = Capture.search([("match_id", "=", match.id)], limit=1)
        if not capture:
            capture = Capture.create({"match_id": match.id, "signature": signature, "payload": {
                "home": match.home_score, "away": match.away_score, "periods": [],
                "outcome": "normal", "reason": "", "zero_confirmed": False}})
        return capture

    def _response(self, capture, match, session):
        return {"match_id": match.id, "revision": capture.revision, "payload": capture.payload,
                "signature": self._signature(match, session), "draft_signature": capture.signature,
                "submitted": capture.submitted, "result_state": match.result_state,
                "review_required": capture.review_required, "closed": capture.closed,
                "undo_available": capture.undo_available, "saved_at": str(capture.write_date)}

    @api.model
    def courts(self):
        accesses = self.env["federation.court.access"].sudo().search([
            ("user_id", "=", self.env.uid), ("active", "=", True)
        ]) if not self.env.user.share else self.env["federation.court.access"]
        return [{"matchday_id": a.matchday_id.id, "court_id": a.court_id.id,
                 "name": "%s / %s" % (a.matchday_id.display_name, a.court_id.display_name)} for a in accesses]

    @api.model
    def load(self, matchday_id, court_id):
        access, session = self._access(matchday_id, court_id)
        matches = self.env["federation.match"].sudo().search([("schedule_publication_id", "=", session.publication_id.id)])
        queue = []
        for match in matches:
            slot = match.operational_slot_id or match.published_slot_id
            if not slot or slot.court_id != access.court_id or match.operational_status in {"cancelled", "postponed"}:
                continue
            queue.append({"id": match.id, "name": match.display_name,
                          "home": match.home_team_id.display_name, "away": match.away_team_id.display_name,
                          "start": str(slot.start_datetime), "end": str(slot.end_datetime),
                          "result_state": match.result_state, "operational_state": match.operational_status,
                          "coverage": match._coverage_snapshot(),
                          "officials": [{"name": a.referee_id.display_name, "role": a.role,
                                        "accepted": a.coverage_accepted, "eligible": a.coverage_eligible,
                                        "present": a.coverage_present} for a in match.referee_assignment_ids if a.state != "cancelled"]})
        queue.sort(key=lambda row: (row["start"], row["id"]))
        return {"queue": queue, "session": session.id, "publication": session.publication_digest,
                "court": access.court_id.display_name, "matchday": access.matchday_id.display_name}

    @api.model
    def open_match(self, matchday_id, court_id, match_id):
        access, session = self._access(matchday_id, court_id)
        match = self._match(access, match_id)
        # Serialize creation with all result mutations on the canonical match row.
        match._lock_result_transition()
        match.invalidate_recordset()
        capture = self._capture(match, self._signature(match, session))
        edition = match._competition_workflow_edition()
        result = self._response(capture, match, session)
        result.update({"mode": edition.court_scoring_mode, "set_target": edition.court_set_target,
                       "max_periods": edition.court_max_periods, "lineups": self._lineups(match)})
        return result

    def _lineups(self, match):
        # Resolve the canonical match sheets; never expose contact or birth data.
        sheets = self.env["federation.match.sheet"].sudo().search([("match_id", "=", match.id)])
        return [{"id": sheet.id, "name": sheet.display_name, "state": sheet.state,
                 "players": [line.player_id.display_name for line in sheet.line_ids]} for sheet in sheets]

    @api.model
    def sync(self, matchday_id, court_id, match_id, commands):
        if not isinstance(commands, list) or not 1 <= len(commands) <= 100:
            raise ValidationError(_("Synchronise 1 to 100 commands at a time."))
        with self.env.cr.savepoint():
            access, session = self._access(matchday_id, court_id)
            match = self._match(access, match_id)
            match._lock_result_transition()
            match.invalidate_recordset()
            capture = self._capture(match, self._signature(match, session))
            capture.invalidate_recordset()
            receipts = self.env["federation.court.receipt"].sudo().with_context(**{_CONTEXT: _TOKEN})
            responses = []
            for command in commands:
                try:
                    validate_command(command)
                except ValueError as error:
                    raise ValidationError(str(error)) from error
                fingerprint = digest(command)
                replay = receipts.search([("capture_id", "=", capture.id), ("key", "=", command["key"])], limit=1)
                if replay:
                    if replay.digest != fingerprint or replay.actor_id != self.env.user:
                        raise ValidationError(_("Idempotency key was reused for different content or actor."))
                    responses.append(replay.response)
                    continue
                if (command["revision"] != capture.revision or command["signature"] != self._signature(match, session)
                        or capture.signature != command["signature"]):
                    raise ValidationError(_("Conflict: schedule, result or draft changed. Keep local evidence and reconcile explicitly."))
                if capture.submitted or capture.closed or match.result_state not in {"draft", "corrected"}:
                    raise ValidationError(_("Submitted or official results cannot be overwritten from court capture."))
                operation = command["operation"]
                if operation == "undo":
                    if not capture.undo_available:
                        raise ValidationError(_("No saved draft is available to undo."))
                    payload = capture.previous_payload
                else:
                    edition = match._competition_workflow_edition()
                    try:
                        payload = validate_capture(command["payload"], edition.court_scoring_mode,
                                                   edition.court_set_target, edition.court_max_periods, complete=operation == "submit")
                    except ValueError as error:
                        raise ValidationError(str(error)) from error
                values = {"payload": payload, "previous_payload": capture.payload,
                          "undo_available": operation != "undo", "revision": capture.revision + 1,
                          "signature": command["signature"]}
                if payload["outcome"] in {"abandoned", "disputed"}:
                    values["review_required"] = True
                if operation == "submit":
                    if capture.review_required:
                        raise ValidationError(_("A coordinator must resolve the dispute or abandonment hold."))
                    if payload["outcome"] in {"interrupted", "abandoned", "disputed"}:
                        raise ValidationError(_("Save this exception for coordinator review; it is not an official result."))
                    self._submit(match, payload)
                    values.update({"submitted": True, "undo_available": False,
                                   "signature": self._signature(match, session)})
                capture.write(values)
                if payload["outcome"] != "normal" and operation != "undo":
                    self.env["federation.matchday.incident"].sudo().create({
                        "matchday_id": access.matchday_id.id, "incident_type": "other", "court_capture_id": capture.id,
                        "description": "%s | %s | %s | command %s" % (
                            match.display_name, payload["outcome"], payload["reason"], command["key"])})
                response = self._response(capture, match, session)
                receipts.create({"capture_id": capture.id, "key": command["key"], "digest": fingerprint,
                                 "actor_id": self.env.uid, "operation": operation, "response": response})
                responses.append(response)
            return {"receipts": responses, "current": self._response(capture, match, session)}

    def _submit(self, match, payload):
        # Authorization has already been checked against the named court operator.
        target = match.with_user(self.env.user).sudo().with_context(**{
            _RESULT_COMMAND_CONTEXT_KEY: _RESULT_COMMAND_TOKEN, _CONTEXT: _TOKEN})
        target.write({"home_score": payload["home"], "away_score": payload["away"],
                      "score_entry_confirmed": True, "zero_zero_confirmed": payload["zero_confirmed"],
                      "court_outcome": payload["outcome"], "court_outcome_reason": payload["reason"]})
        target.result_period_ids.unlink()
        edition = target._competition_workflow_edition()
        for index, period in enumerate(payload["periods"], 1):
            home, away = period["home"], period["away"]
            if edition.court_scoring_mode == "sets":
                home, away = int(home > away), int(away > home)
            target.env["federation.match.result.period"].create({"match_id": target.id, "sequence": index,
                "home_score": home, "away_score": away,
                "note": "Raw set: %s:%s" % (period["home"], period["away"])})
        target.action_submit_result()

    @api.model
    def reconcile(self, matchday_id, court_id, match_id, revision, reason):
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise ValidationError(_("Record why the draft remains valid."))
        with self.env.cr.savepoint():
            access, session = self._access(matchday_id, court_id)
            match = self._match(access, match_id)
            match._lock_result_transition()
            match.invalidate_recordset()
            capture = self._capture(match, self._signature(match, session))
            capture.invalidate_recordset()
            if capture.revision != int(revision) or capture.submitted or match.result_state not in {"draft", "corrected"}:
                raise ValidationError(_("The draft changed or is no longer mutable."))
            capture.write({"signature": self._signature(match, session), "revision": capture.revision + 1})
            response = self._response(capture, match, session)
            self.env["federation.court.receipt"].sudo().with_context(**{_CONTEXT: _TOKEN}).create({
                "capture_id": capture.id, "key": "reconcile:%s" % capture.revision,
                "digest": digest({"reason": reason, "revision": capture.revision}), "actor_id": self.env.uid,
                "operation": "reconcile", "response": {**response, "reason": reason.strip()}})
            return response


class CourtIncident(models.Model):
    _inherit = "federation.matchday.incident"
    court_capture_id = fields.Many2one("federation.court.capture", readonly=True, ondelete="restrict", index=True)


class ResolveCourtException(models.TransientModel):
    _name = "federation.court.resolve.wizard"
    _description = "Resolve Court Exception"
    capture_id = fields.Many2one("federation.court.capture", required=True, readonly=True)
    expected_revision = fields.Integer(required=True, readonly=True)
    disposition = fields.Selection([("resume", "Resume or reopen capture"),
        ("abandoned", "Confirm abandonment without an official score")], required=True)
    reason = fields.Text(required=True)

    def action_resolve(self):
        self.ensure_one()
        if not (self.reason or "").strip() or len(self.reason) > 2000:
            raise ValidationError(_("Record the coordinator decision."))
        if not self.env.user.has_group("sports_federation_matchday.group_matchday_manager"):
            raise AccessError(_("Only match-day managers resolve court holds."))
        capture = self.capture_id
        match = capture.match_id
        self.env["federation.competition.role.assignment"].assert_role(
            match._competition_workflow_edition(), "matchday_manager", "competition_director")
        with self.env.cr.savepoint():
            match._lock_result_transition()
            capture.invalidate_recordset()
            if capture.revision != self.expected_revision or capture.submitted:
                raise ValidationError(_("Court evidence changed. Open a new decision preview."))
            payload = dict(capture.payload)
            payload.update({"outcome": "normal" if self.disposition == "resume" else "abandoned",
                            "reason": self.reason.strip()})
            capture = capture.sudo().with_context(**{_CONTEXT: _TOKEN})
            capture.write({"payload": payload, "previous_payload": capture.payload,
                "revision": capture.revision + 1, "review_required": False,
                "closed": self.disposition == "abandoned", "undo_available": False})
            self.env["federation.court.receipt"].sudo().with_context(**{_CONTEXT: _TOKEN}).create({
                "capture_id": capture.id, "key": "decision:%s" % capture.revision,
                "digest": digest({"reason": self.reason, "disposition": self.disposition}),
                "actor_id": self.env.uid, "operation": "coordinator_decision",
                "response": {"revision": capture.revision, "payload": payload, "closed": capture.closed}})
            for incident in self.env["federation.matchday.incident"].search([
                ("court_capture_id", "=", capture.id), ("resolved", "=", False)]):
                self.env["federation.matchday.commands"].resolve_incident(incident.id)
        return {"type": "ir.actions.act_window_close"}
