import json
import logging
from uuid import uuid4

from odoo import _, fields
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class CompetitionWorkspacePlannerStateMixin:
    def _ensure_planner_write_revision(self, gameday, expected_planner_revision=False):
        planner_root = self._get_planner_root_gameday(gameday)
        normalized_revision = self._normalize_expected_planner_revision(
            expected_planner_revision
        )
        planner_root._competition_workspace_check_revision(normalized_revision)
        return planner_root

    def _planner_write_conflict_payload(
        self,
        planner_root,
        operation,
        expected_planner_revision=False,
        code="stale_planner_revision",
        message=False,
    ):
        correlation_id = uuid4().hex[:12]
        _logger.warning(
            "Planner write conflict for %s (correlation_id=%s, expected=%s, current=%s)",
            operation,
            correlation_id,
            expected_planner_revision,
            planner_root.planner_revision,
        )
        return {
            "ok": False,
            "validation": self._planner_blocking_validation(
                code,
                message
                or _(
                    "The planner data is stale for this write operation. Refresh and retry."
                ),
                record_id=planner_root.id,
            ),
            "conflict": {
                "code": code,
                "operation": operation,
                "expected_planner_revision": expected_planner_revision or False,
                "current_planner_revision": planner_root.planner_revision,
                "correlation_id": correlation_id,
            },
            "diagnostics": {"correlation_id": correlation_id},
        }

    def _ensure_planner_write_revision_or_conflict(
        self,
        gameday,
        expected_planner_revision=False,
        operation="planner_write",
    ):
        planner_root = self._get_planner_root_gameday(gameday)
        try:
            normalized_revision = self._normalize_expected_planner_revision(
                expected_planner_revision
            )
        except ValidationError:
            return (
                False,
                self._planner_write_conflict_payload(
                    planner_root,
                    operation,
                    expected_planner_revision=expected_planner_revision,
                    code="invalid_planner_revision",
                    message=_("The planner revision token is invalid."),
                ),
            )

        try:
            planner_root._competition_workspace_check_revision(normalized_revision)
        except ValidationError:
            return (
                False,
                self._planner_write_conflict_payload(
                    planner_root,
                    operation,
                    expected_planner_revision=normalized_revision,
                ),
            )
        return planner_root, False

    def _bump_planner_revision(self, gameday):
        planner_root = self._get_planner_root_gameday(gameday)
        planner_root._competition_workspace_bump_revision()
        if planner_root.schedule_draft_revision_id:
            self._refresh_schedule_revision(
                planner_root.schedule_draft_revision_id,
                planner_root,
            )
        return True

    def _planner_operation_model(self):
        return self.env["federation.competition.planner.operation"]

    def _schedule_revision_model(self):
        return self.env["federation.competition.schedule.revision"]

    def _workspace_presence_model(self):
        return self.env["federation.competition.workspace.presence"]

    def _normalize_expected_planner_revision(self, expected_planner_revision=False):
        if expected_planner_revision in (False, None):
            return False
        if isinstance(expected_planner_revision, str):
            expected_planner_revision = expected_planner_revision.strip()
            if not expected_planner_revision:
                return False
        try:
            return int(expected_planner_revision)
        except (TypeError, ValueError):
            raise ValidationError(_("The planner revision token is invalid."))

    def _normalize_idempotency_key(self, idempotency_key=False):
        if idempotency_key in (False, None):
            return False
        key = str(idempotency_key).strip()
        if not key:
            return False
        if len(key) > 120:
            raise ValidationError(_("The idempotency key is too long."))
        return key

    def _idempotency_batch_key(self, scope, idempotency_key=False):
        key = self._normalize_idempotency_key(idempotency_key)
        if not key:
            return False
        return "idem:%s:%s" % (scope, key)

    def _idempotency_metadata(self, scope, idempotency_key=False, replayed=False):
        key = self._normalize_idempotency_key(idempotency_key)
        if not key:
            return False
        return {
            "scope": scope,
            "key": key,
            "replayed": bool(replayed),
        }

    def _idempotency_replay_response(
        self,
        planner_root,
        scope,
        idempotency_key=False,
    ):
        return {
            "ok": True,
            "replayed": True,
            "idempotency": self._idempotency_metadata(
                scope,
                idempotency_key=idempotency_key,
                replayed=True,
            ),
            "planner": self.get_gameday_planner_data(planner_root.id),
        }

    def _idempotency_applied_operations(
        self, planner_root, scope, idempotency_key=False
    ):
        batch_key = self._idempotency_batch_key(scope, idempotency_key=idempotency_key)
        if not batch_key:
            return self._planner_operation_model().browse()
        return self._planner_operation_model().search(
            [
                ("planner_root_round_id", "=", planner_root.id),
                ("batch_key", "=", batch_key),
                ("state", "=", "applied"),
            ],
            order="id asc",
        )

    def _idempotency_applied_operations_for_match(
        self,
        match,
        scope,
        idempotency_key=False,
    ):
        batch_key = self._idempotency_batch_key(scope, idempotency_key=idempotency_key)
        if not batch_key:
            return self._planner_operation_model().browse()
        return self._planner_operation_model().search(
            [
                ("match_id", "=", match.id),
                ("batch_key", "=", batch_key),
                ("state", "=", "applied"),
            ],
            order="id asc",
        )

    def _assert_idempotent_assign_intent(self, operations, match, slot):
        if not operations:
            return False
        if not operations.filtered(lambda operation: operation.match_id == match):
            raise ValidationError(
                _(
                    "The idempotency key was reused for a different match assignment request."
                )
            )
        if not operations.filtered(
            lambda operation: operation.new_slot_id and operation.new_slot_id == slot
        ):
            raise ValidationError(
                _("The idempotency key was reused for a different target slot.")
            )
        return True

    def _assert_idempotent_unassign_intent(self, operations, match):
        if not operations:
            return False
        if not operations.filtered(
            lambda operation: operation.match_id == match
            and operation.operation_type == "unassign"
        ):
            raise ValidationError(
                _("The idempotency key was reused for a different unassign request.")
            )
        return True

    def _next_schedule_revision_number(self, planner_root):
        latest_revision = self._schedule_revision_model().search(
            [("planner_root_round_id", "=", planner_root.id)],
            order="revision_number desc, id desc",
            limit=1,
        )
        return (latest_revision.revision_number or 0) + 1

    def _schedule_revision_metrics(self, planner_root):
        validation = self.validate_gameday(planner_root.id)
        return {
            "slot_count": len(planner_root.slot_ids),
            "assigned_match_count": len(planner_root.slot_ids.filtered("match_id")),
            "warning_count": len(validation["warnings"]),
        }

    def _build_schedule_revision_snapshot(self, planner_root):
        slots = planner_root.slot_ids.sorted(
            lambda record: (
                record.start_datetime,
                record.playing_area_id.name or "",
                record.id,
            )
        )
        payload = {
            "planner_root_round_id": planner_root.id,
            "planner_state": planner_root.planner_state,
            "planner_revision": planner_root.planner_revision,
            "round_date": self._serialize_date(planner_root.round_date),
            "slots": [
                {
                    "slot_id": slot.id,
                    "start_datetime": self._serialize_datetime(slot.start_datetime),
                    "end_datetime": self._serialize_datetime(slot.end_datetime),
                    "state": slot.state,
                    "court_id": (
                        slot.playing_area_id.id if slot.playing_area_id else False
                    ),
                    "court_name": (
                        slot.playing_area_id.display_name
                        if slot.playing_area_id
                        else False
                    ),
                    "match_id": slot.match_id.id if slot.match_id else False,
                    "match_name": (
                        slot.match_id.display_name if slot.match_id else False
                    ),
                    "division_id": (
                        slot.match_id.tournament_id.id
                        if slot.match_id and slot.match_id.tournament_id
                        else False
                    ),
                }
                for slot in slots
            ],
        }
        return json.dumps(payload, sort_keys=True)

    def _refresh_schedule_revision(self, revision, planner_root, override_reason=False):
        metrics = self._schedule_revision_metrics(planner_root)
        write_vals = {
            "snapshot_payload": self._build_schedule_revision_snapshot(planner_root),
            **metrics,
        }
        normalized_reason = self._normalize_override_reason(override_reason)
        if normalized_reason:
            write_vals["override_reason"] = normalized_reason
        revision.write(write_vals)
        return revision

    def _ensure_draft_schedule_revision(self, gameday):
        planner_root = self._get_planner_root_gameday(gameday)
        draft_revision = planner_root.schedule_draft_revision_id
        if draft_revision and draft_revision.state == "draft":
            return self._refresh_schedule_revision(draft_revision, planner_root)

        revision_number = self._next_schedule_revision_number(planner_root)

        draft_revision = self._schedule_revision_model().create(
            {
                "name": _(
                    "Revision %(number)s",
                    number=revision_number,
                ),
                "planner_root_round_id": planner_root.id,
                "edition_id": planner_root.tournament_id.edition_id.id,
                "revision_number": revision_number,
                "state": "draft",
                "based_on_revision_id": planner_root.schedule_live_revision_id.id,
            }
        )
        planner_root.write({"schedule_draft_revision_id": draft_revision.id})
        return self._refresh_schedule_revision(draft_revision, planner_root)

    def _promote_schedule_revision_to_live(self, gameday, override_reason=False):
        planner_root = self._get_planner_root_gameday(gameday)
        current_live_revision = planner_root.schedule_live_revision_id
        draft_revision = (
            planner_root.schedule_draft_revision_id
            or self._ensure_draft_schedule_revision(planner_root)
        )
        normalized_reason = self._normalize_override_reason(override_reason)
        self._refresh_schedule_revision(
            draft_revision,
            planner_root,
            override_reason=normalized_reason,
        )
        if current_live_revision and current_live_revision != draft_revision:
            current_live_revision.write({"state": "superseded"})
        draft_revision.write(
            {
                "state": "live",
                "published_on": fields.Datetime.now(),
                "published_by_id": self.env.user.id,
                "override_reason": normalized_reason
                or draft_revision.override_reason
                or False,
            }
        )
        planner_root.write(
            {
                "schedule_live_revision_id": draft_revision.id,
                "schedule_draft_revision_id": False,
            }
        )
        return draft_revision

    def _serialize_schedule_revision(self, revision):
        if not revision:
            return False
        return {
            "id": revision.id,
            "name": revision.name,
            "revision_number": revision.revision_number,
            "state": revision.state,
            "state_label": self._get_state_label(revision, "state", revision.state),
            "based_on_revision_id": revision.based_on_revision_id.id,
            "based_on_revision_number": revision.based_on_revision_id.revision_number,
            "published_on": self._serialize_datetime(revision.published_on),
            "published_by_name": (
                revision.published_by_id.display_name
                if revision.published_by_id
                else False
            ),
            "override_reason": revision.override_reason or False,
            "slot_count": revision.slot_count,
            "assigned_match_count": revision.assigned_match_count,
            "warning_count": revision.warning_count,
        }

    def _serialize_schedule_revision_summary(self, gameday, limit=6):
        planner_root = self._get_planner_root_gameday(gameday)
        revisions = self._schedule_revision_model().search(
            [("planner_root_round_id", "=", planner_root.id)],
            order="revision_number desc, id desc",
            limit=limit,
        )
        return {
            "live_revision": self._serialize_schedule_revision(
                planner_root.schedule_live_revision_id
            ),
            "draft_revision": self._serialize_schedule_revision(
                planner_root.schedule_draft_revision_id
            ),
            "recent_revisions": [
                self._serialize_schedule_revision(revision) for revision in revisions
            ],
            "has_pending_draft_changes": bool(planner_root.schedule_draft_revision_id),
            "requires_republish_reason": bool(planner_root.schedule_live_revision_id),
        }
