"""Scoped court capture with immutable receipts and optimistic concurrency."""

from odoo import _, api, models
from odoo.exceptions import ValidationError
from odoo.addons.sports_federation_result_control.services.result_commands import (
    _RESULT_COMMAND_CONTEXT_KEY,
    _RESULT_COMMAND_TOKEN,
)
from ..policy import digest, set_points, validate_capture, validate_command


from .court import _TOKEN, _CONTEXT


class CourtCommandsExtension(models.AbstractModel):
    _inherit = "federation.court.commands"

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
            return self._apply_commands(match, session, capture, commands)

    def _apply_commands(self, match, session, capture, commands, device=None):
        """Apply validated court commands to one capture, with receipts.

        Shared by the backend court app (``sync``) and the offline device API.
        The device API checks the device signature instead of the session
        signature, because a phone can download its game day before the
        session opens; it also records the device on every receipt.
        """
        receipts = (
            self.env["federation.court.receipt"]
            .sudo()
            .with_context(**{_CONTEXT: _TOKEN})
        )
        responses = []
        for command in commands:
            try:
                validate_command(command)
            except ValueError as error:
                raise ValidationError(str(error)) from error
            fingerprint = digest(command)
            replay = receipts.search(
                [("capture_id", "=", capture.id), ("key", "=", command["key"])],
                limit=1,
            )
            if replay:
                if replay.digest != fingerprint or replay.actor_id != self.env.user:
                    raise ValidationError(
                        _("Idempotency key was reused for different content or actor.")
                    )
                responses.append(replay.response)
                continue
            if device:
                # Phones score against the device signature. Journals moved
                # from the backend court app carry the session signature,
                # which is just as strict.
                stale = command["revision"] != capture.revision or command[
                    "signature"
                ] not in (
                    self._device_signature(match),
                    self._signature(match, session),
                )
            else:
                stale = (
                    command["revision"] != capture.revision
                    or command["signature"] != self._signature(match, session)
                    or capture.signature != command["signature"]
                )
            if stale:
                raise ValidationError(
                    _(
                        "Conflict: schedule, result or draft changed. Keep local evidence and reconcile explicitly."
                    )
                )
            if (
                capture.submitted
                or capture.closed
                or match.result_state not in {"draft", "corrected"}
            ):
                raise ValidationError(
                    _(
                        "Submitted or official results cannot be overwritten from court capture."
                    )
                )
            operation = command["operation"]
            if operation == "undo":
                if not capture.undo_available:
                    raise ValidationError(_("No saved draft is available to undo."))
                payload = capture.previous_payload
            else:
                edition = match._competition_workflow_edition()
                try:
                    payload = validate_capture(
                        command["payload"],
                        edition.court_scoring_mode,
                        edition.court_set_target,
                        edition.court_max_periods,
                        complete=operation == "submit",
                        win_points=edition.court_set_win_points,
                        draw_points=edition.court_set_draw_points,
                    )
                except ValueError as error:
                    raise ValidationError(str(error)) from error
            values = {
                "payload": payload,
                "previous_payload": capture.payload,
                "undo_available": operation != "undo",
                "revision": capture.revision + 1,
                "signature": self._signature(match, session),
            }
            values.update(self._command_evidence(match, capture, device))
            if payload["outcome"] in {"abandoned", "disputed"}:
                values["review_required"] = True
            if operation == "submit":
                if capture.review_required:
                    raise ValidationError(
                        _("A coordinator must resolve the dispute or abandonment hold.")
                    )
                if payload["outcome"] in {"interrupted", "abandoned", "disputed"}:
                    raise ValidationError(
                        _(
                            "Save this exception for coordinator review; it is not an official result."
                        )
                    )
                self._submit(match, payload)
                values.update(
                    {
                        "submitted": True,
                        "undo_available": False,
                        "signature": self._signature(match, session),
                    }
                )
            capture.write(values)
            if payload["outcome"] != "normal" and operation != "undo":
                self.env["federation.matchday.incident"].sudo().create(
                    {
                        "matchday_id": session.matchday_id.id,
                        "incident_type": "other",
                        "court_capture_id": capture.id,
                        "description": "%s | %s | %s | command %s"
                        % (
                            match.display_name,
                            payload["outcome"],
                            payload["reason"],
                            command["key"],
                        ),
                    }
                )
            response = self._response(capture, match, session)
            receipts.create(
                {
                    "capture_id": capture.id,
                    "key": command["key"],
                    "digest": fingerprint,
                    "actor_id": self.env.uid,
                    "operation": operation,
                    "response": response,
                    "device_id": device.id if device else False,
                }
            )
            responses.append(response)
        return {
            "receipts": responses,
            "acknowledged_keys": [command["key"] for command in commands],
            "current": self._response(capture, match, session),
        }

    def _command_evidence(self, match, capture, device):
        """Who scored, from which source, on which device (for the check screen)."""
        source, club = match._court_scoring_source(self.env.user)
        return {
            "scorer_user_id": self.env.uid,
            "scorer_source": source or "court_operator",
            "scorer_club_id": club.id if club else False,
            "device_id": device.id if device else capture.device_id.id,
        }

    def _submit(self, match, payload):
        # Authorization has already been checked against the named court operator.
        # Court results always wait for the tournament manager's approval.
        target = (
            match.with_user(self.env.user)
            .sudo()
            .with_context(
                **{
                    _RESULT_COMMAND_CONTEXT_KEY: _RESULT_COMMAND_TOKEN,
                    _CONTEXT: _TOKEN,
                    "result_manager_review_required": True,
                }
            )
        )
        target.write(
            {
                "home_score": payload["home"],
                "away_score": payload["away"],
                "score_entry_confirmed": True,
                "zero_zero_confirmed": payload["zero_confirmed"],
                "court_outcome": payload["outcome"],
                "court_outcome_reason": payload["reason"],
            }
        )
        target.result_period_ids.unlink()
        edition = target._competition_workflow_edition()
        for index, period in enumerate(payload["periods"], 1):
            home, away = period["home"], period["away"]
            if edition.court_scoring_mode == "sets":
                home, away = set_points(
                    period,
                    edition.court_set_win_points,
                    edition.court_set_draw_points,
                )
            target.env["federation.match.result.period"].create(
                {
                    "match_id": target.id,
                    "sequence": index,
                    "home_score": home,
                    "away_score": away,
                    "note": "Raw set: %s:%s" % (period["home"], period["away"]),
                }
            )
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
            if (
                capture.revision != int(revision)
                or capture.submitted
                or match.result_state not in {"draft", "corrected"}
            ):
                raise ValidationError(_("The draft changed or is no longer mutable."))
            capture.write(
                {
                    "signature": self._signature(match, session),
                    "revision": capture.revision + 1,
                }
            )
            response = self._response(capture, match, session)
            self.env["federation.court.receipt"].sudo().with_context(
                **{_CONTEXT: _TOKEN}
            ).create(
                {
                    "capture_id": capture.id,
                    "key": "reconcile:%s" % capture.revision,
                    "digest": digest({"reason": reason, "revision": capture.revision}),
                    "actor_id": self.env.uid,
                    "operation": "reconcile",
                    "response": {**response, "reason": reason.strip()},
                }
            )
            return response
