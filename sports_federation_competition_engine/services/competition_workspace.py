import json
import logging
from datetime import datetime, timedelta, time
from uuid import uuid4

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


_logger = logging.getLogger(__name__)


class PlannerOperationRollback(Exception):
    def __init__(self, result):
        super().__init__("Planner operation rolled back")
        self.result = result


class CompetitionWorkspaceService(models.AbstractModel):
    _name = "federation.competition.workspace.service"
    _description = "Competition Workspace Service"

    _pool_bracket_progression_sequence_gap = 10
    _workspace_extension_schema_versions = (1,)

    def _check_access(self, require_publish=False):
        return self.env["federation.tournament"]._competition_workspace_check_access(
            user=self.env.user,
            require_publish=require_publish,
        )

    def _validation_service(self):
        return self.env["federation.competition.workspace.validation.service"]

    def _read_model_service(self):
        return self.env["federation.competition.workspace.read.model.service"]

    def _workspace_extension_models(self):
        return [
            self.env[model_name]
            for model_name in sorted(self.env.registry.models)
            if model_name.startswith("federation.competition.workspace.extension.")
        ]

    def _workspace_extension_results(self, method_name, *args, **kwargs):
        telemetry = kwargs.pop("_telemetry", None)
        warning_bucket = kwargs.pop("_warning_bucket", None)
        results = []
        for extension in self._workspace_extension_models():
            method = getattr(extension, method_name, None)
            if not callable(method):
                continue
            try:
                result = method(self, *args, **kwargs)
            except Exception as error:  # pylint: disable=broad-except
                correlation_id = uuid4().hex[:12]
                if isinstance(telemetry, list):
                    telemetry.append(
                        {
                            "method": method_name,
                            "extension_model": extension._name,
                            "status": "error",
                            "error_type": type(error).__name__,
                            "correlation_id": correlation_id,
                        }
                    )
                if isinstance(warning_bucket, list):
                    warning_bucket.append(
                        self._workspace_extension_failure_warning(
                            method_name,
                            extension._name,
                            correlation_id=correlation_id,
                        )
                    )
                _logger.exception(
                    "Workspace extension hook failed for %s on %s (correlation_id=%s)",
                    method_name,
                    extension._name,
                    correlation_id,
                )
                continue

            if isinstance(telemetry, list):
                telemetry.append(
                    {
                        "method": method_name,
                        "extension_model": extension._name,
                        "status": "ok",
                        "emitted": bool(result),
                    }
                )
            if result:
                results.append(result)

        if isinstance(telemetry, list):
            self._log_workspace_extension_telemetry(method_name, telemetry)
        return results

    def _workspace_extension_failure_warning(
        self,
        method_name,
        extension_model,
        correlation_id=False,
    ):
        return {
            "code": "extension_hook_failed",
            "message": _(
                "An extension hook failed and was ignored while computing workspace data."
            ),
            "hook": method_name,
            "extension_model": extension_model,
            "correlation_id": correlation_id or uuid4().hex[:12],
        }

    def _normalize_workspace_extension_schema_version(self, result, method_name):
        if not isinstance(result, dict) or "schema_version" not in result:
            return 1
        try:
            schema_version = int(result.get("schema_version"))
        except (TypeError, ValueError):
            _logger.warning(
                "Workspace extension output ignored for %s: invalid schema_version %s",
                method_name,
                result.get("schema_version"),
            )
            return False

        if schema_version not in self._workspace_extension_schema_versions:
            _logger.warning(
                "Workspace extension output ignored for %s: unsupported schema_version %s",
                method_name,
                schema_version,
            )
            return False
        return schema_version

    def _normalize_workspace_extension_payload_result(self, result, method_name):
        schema_version = self._normalize_workspace_extension_schema_version(
            result,
            method_name,
        )
        if not schema_version:
            return {}
        if schema_version == 1 and isinstance(result, dict) and "schema_version" in result:
            payload = result.get("payload")
            if payload is None:
                return {}
            if isinstance(payload, dict):
                return payload
            _logger.warning(
                "Workspace extension payload ignored for %s: schema payload must be dict",
                method_name,
            )
            return {}
        return result

    def _normalize_workspace_extension_issue_result(self, result, method_name):
        schema_version = self._normalize_workspace_extension_schema_version(
            result,
            method_name,
        )
        if not schema_version:
            return {}
        if schema_version == 1 and isinstance(result, dict) and "schema_version" in result:
            issues = result.get("issues")
            if issues is None:
                return {}
            if isinstance(issues, dict):
                return issues
            _logger.warning(
                "Workspace extension issues ignored for %s: schema issues must be dict",
                method_name,
            )
            return {}
        return result

    def _normalize_workspace_extension_score_result(self, result, method_name):
        schema_version = self._normalize_workspace_extension_schema_version(
            result,
            method_name,
        )
        if not schema_version:
            return []
        if schema_version == 1 and isinstance(result, dict) and "schema_version" in result:
            components = result.get("components")
            if components is None:
                return []
            if isinstance(components, dict):
                return [components]
            if isinstance(components, (list, tuple, set)):
                return list(components)
            _logger.warning(
                "Workspace extension score components ignored for %s: schema components must be list/dict",
                method_name,
            )
            return []
        return result

    def _log_workspace_extension_telemetry(self, method_name, telemetry):
        if not telemetry:
            return
        failed = [entry for entry in telemetry if entry.get("status") == "error"]
        if failed:
            _logger.warning(
                "Workspace extension telemetry for %s: %s hook(s) failed out of %s",
                method_name,
                len(failed),
                len(telemetry),
            )
        else:
            _logger.debug(
                "Workspace extension telemetry for %s: %s hook(s) executed",
                method_name,
                len(telemetry),
            )

    def _merge_workspace_payload(self, payload, update):
        merged = dict(payload or {})
        for key, value in (update or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._merge_workspace_payload(merged[key], value)
            elif isinstance(value, list) and isinstance(merged.get(key), list):
                merged[key] = merged[key] + value
            else:
                merged[key] = value
        return merged

    def _workspace_extension_payload(self, method_name, *args, **kwargs):
        payload = {}
        telemetry = []
        for update in self._workspace_extension_results(
            method_name,
            *args,
            _telemetry=telemetry,
            **kwargs,
        ):
            update = self._normalize_workspace_extension_payload_result(
                update,
                method_name,
            )
            normalized_update = self._normalize_workspace_extension_payload_update(
                update,
                method_name=method_name,
            )
            payload = self._merge_workspace_payload(payload, normalized_update)
        return payload

    def _normalize_workspace_extension_payload_update(self, update, method_name):
        if not update:
            return {}
        if not isinstance(update, dict):
            _logger.warning(
                "Workspace extension payload ignored for %s: expected dict, got %s",
                method_name,
                type(update).__name__,
            )
            return {}
        return update

    def _workspace_extension_issues(self, method_name, *args, **kwargs):
        issues = {"blocking": [], "warnings": []}
        extension_warnings = []
        telemetry = []
        for result in self._workspace_extension_results(
            method_name,
            *args,
            _warning_bucket=extension_warnings,
            _telemetry=telemetry,
            **kwargs,
        ):
            result = self._normalize_workspace_extension_issue_result(
                result,
                method_name,
            )
            if not isinstance(result, dict):
                _logger.warning(
                    "Workspace extension issues ignored for %s: expected dict, got %s",
                    method_name,
                    type(result).__name__,
                )
                continue
            blocking_issues = self._normalize_workspace_extension_issue_bucket(
                result.get("blocking"),
                method_name=method_name,
                severity="blocking",
            )
            warning_issues = self._normalize_workspace_extension_issue_bucket(
                result.get("warnings"),
                method_name=method_name,
                severity="warning",
            )

            for issue in blocking_issues:
                severity = self._validation_service().normalize_issue_severity(
                    issue.get("severity"),
                    default="blocking",
                )
                if severity == "blocking":
                    issues["blocking"].append(issue)
                else:
                    issues["warnings"].append(issue)

            for issue in warning_issues:
                severity = self._validation_service().normalize_issue_severity(
                    issue.get("severity"),
                    default="warning",
                )
                if severity == "blocking":
                    issues["blocking"].append(issue)
                else:
                    issues["warnings"].append(issue)
        issues["warnings"].extend(extension_warnings)
        return issues

    def _safe_workspace_issue_int(self, raw_value):
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return False

    def _normalize_workspace_extension_issue(self, issue, method_name, severity):
        if not isinstance(issue, dict):
            _logger.warning(
                "Workspace extension issue ignored for %s (%s): expected dict, got %s",
                method_name,
                severity,
                type(issue).__name__,
            )
            return False

        code = str(issue.get("code") or "").strip()
        message = str(issue.get("message") or "").strip()
        if not code or not message:
            _logger.warning(
                "Workspace extension issue ignored for %s (%s): missing code/message",
                method_name,
                severity,
            )
            return False

        normalized = dict(issue)
        normalized["code"] = code
        normalized["message"] = message

        for key in ("record_id", "match_id", "slot_id", "focus_record_id", "referee_id"):
            if key not in issue:
                continue
            parsed = self._safe_workspace_issue_int(issue.get(key))
            if parsed:
                normalized[key] = parsed
            else:
                normalized.pop(key, None)

        team_ids = issue.get("team_ids")
        if isinstance(team_ids, (list, tuple, set)):
            parsed_team_ids = {
                team_id
                for team_id in (self._safe_workspace_issue_int(value) for value in team_ids)
                if team_id
            }
            if parsed_team_ids:
                normalized["team_ids"] = sorted(parsed_team_ids)
            else:
                normalized.pop("team_ids", None)
        elif "team_ids" in normalized:
            normalized.pop("team_ids", None)

        return normalized

    def _normalize_workspace_extension_issue_bucket(self, raw_issues, method_name, severity):
        if not raw_issues:
            return []
        if isinstance(raw_issues, dict):
            raw_issues = [raw_issues]
        if not isinstance(raw_issues, (list, tuple, set)):
            _logger.warning(
                "Workspace extension issue bucket ignored for %s (%s): expected list/dict, got %s",
                method_name,
                severity,
                type(raw_issues).__name__,
            )
            return []

        normalized_issues = []
        for issue in raw_issues:
            normalized = self._normalize_workspace_extension_issue(
                issue,
                method_name=method_name,
                severity=severity,
            )
            if normalized:
                normalized_issues.append(normalized)
        return normalized_issues

    def _workspace_extension_score_components(self, method_name, *args, **kwargs):
        components = []
        telemetry = []
        for result in self._workspace_extension_results(
            method_name,
            *args,
            _telemetry=telemetry,
            **kwargs,
        ):
            result = self._normalize_workspace_extension_score_result(
                result,
                method_name,
            )
            if isinstance(result, dict):
                result = [result]
            elif not isinstance(result, (list, tuple, set)):
                _logger.warning(
                    "Workspace extension score components ignored for %s: expected list/dict, got %s",
                    method_name,
                    type(result).__name__,
                )
                continue

            for component in result:
                normalized_component = self._normalize_workspace_extension_score_component(
                    component,
                    method_name=method_name,
                )
                if normalized_component:
                    components.append(normalized_component)
        return components

    def _normalize_workspace_extension_score_component(self, component, method_name):
        if not isinstance(component, dict):
            _logger.warning(
                "Workspace extension score component ignored for %s: expected dict, got %s",
                method_name,
                type(component).__name__,
            )
            return False

        key = str(component.get("key") or "").strip()
        if not key:
            _logger.warning(
                "Workspace extension score component ignored for %s: missing key",
                method_name,
            )
            return False

        label = str(component.get("label") or "").strip() or key.replace("_", " ").title()
        raw_score = component.get("score", 100)
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            score = 100
        score = max(0, min(100, round(score)))

        normalized = dict(component)
        normalized["key"] = key
        normalized["label"] = label
        normalized["score"] = score
        return normalized

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

    def _copy_validation_result(self, validation):
        return {
            "valid": validation.get("valid", not validation.get("blocking")),
            "blocking": list(validation.get("blocking") or []),
            "warnings": list(validation.get("warnings") or []),
            "unscheduled_matches": list(validation.get("unscheduled_matches") or []),
            "empty_slots": list(validation.get("empty_slots") or []),
        }

    def _planner_validation(self, blocking=None, warnings=None):
        return self._validation_service().finalize_validation_result(
            {
                "valid": not (blocking or []),
                "blocking": blocking or [],
                "warnings": warnings or [],
                "unscheduled_matches": [],
                "empty_slots": [],
            }
        )

    def _planner_issue_signature(self, issue):
        team_ids = issue.get("team_ids")
        normalized_team_ids = ()
        if isinstance(team_ids, (list, tuple, set)):
            normalized_team_ids = tuple(sorted(team_ids))
        return (
            issue.get("code"),
            issue.get("record_id"),
            issue.get("match_id"),
            issue.get("slot_id"),
            issue.get("message"),
            normalized_team_ids,
        )

    def _planner_override_reason_required(self, validation, message, record_id=False):
        payload = self._copy_validation_result(validation)
        payload["blocking"].append(
            {
                "code": "override_reason_required",
                "message": message,
                "record_id": record_id,
            }
        )
        payload["valid"] = False
        return self._validation_service().finalize_validation_result(payload)

    def _planner_blocking_validation(self, code, message, record_id=False):
        return self._planner_validation(
            blocking=[
                {
                    "code": code,
                    "message": message,
                    "record_id": record_id,
                }
            ]
        )

    def _merge_planner_validations(self, *validations):
        payload = {
            "valid": True,
            "blocking": [],
            "warnings": [],
            "unscheduled_matches": [],
            "empty_slots": [],
        }
        blocking_seen = set()
        warning_seen = set()
        for validation in validations:
            copied = self._copy_validation_result(validation or {})
            for issue in copied["blocking"]:
                signature = self._planner_issue_signature(issue)
                if signature in blocking_seen:
                    continue
                blocking_seen.add(signature)
                payload["blocking"].append(issue)
            for issue in copied["warnings"]:
                signature = self._planner_issue_signature(issue)
                if signature in warning_seen:
                    continue
                warning_seen.add(signature)
                payload["warnings"].append(issue)
            payload["unscheduled_matches"].extend(copied["unscheduled_matches"])
            payload["empty_slots"].extend(copied["empty_slots"])
        payload["valid"] = not payload["blocking"]
        return self._validation_service().finalize_validation_result(payload)

    def _normalize_override_reason(self, override_reason):
        return (override_reason or "").strip()

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

    def _idempotency_applied_operations(self, planner_root, scope, idempotency_key=False):
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
                _("The idempotency key was reused for a different match assignment request.")
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
                    "court_id": slot.playing_area_id.id if slot.playing_area_id else False,
                    "court_name": slot.playing_area_id.display_name
                    if slot.playing_area_id
                    else False,
                    "match_id": slot.match_id.id if slot.match_id else False,
                    "match_name": slot.match_id.display_name if slot.match_id else False,
                    "division_id": slot.match_id.tournament_id.id
                    if slot.match_id and slot.match_id.tournament_id
                    else False,
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
        draft_revision = planner_root.schedule_draft_revision_id or self._ensure_draft_schedule_revision(
            planner_root
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
                "override_reason": normalized_reason or draft_revision.override_reason or False,
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
            "published_by_name": revision.published_by_id.display_name
            if revision.published_by_id
            else False,
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

    def _coerce_workspace_competition(self, competition=False, division=False, gameday=False):
        if competition:
            return competition if hasattr(competition, "_name") else self._resolve_competition(competition)
        if division:
            division = division if hasattr(division, "_name") else self._resolve_division(division)
            return division.edition_id
        if gameday:
            gameday = gameday if hasattr(gameday, "_name") else self._resolve_gameday(gameday)
            return gameday.tournament_id.edition_id
        return False

    def _normalize_presence_section(self, active_section):
        allowed_sections = {"overview", "teams", "rounds", "gamedays", "planner", "publish"}
        return active_section if active_section in allowed_sections else "overview"

    def _touch_workspace_presence(
        self,
        competition=False,
        division=False,
        gameday=False,
        active_section="overview",
    ):
        competition = self._coerce_workspace_competition(
            competition=competition,
            division=division,
            gameday=gameday,
        )
        if not competition:
            return False
        division = division if hasattr(division, "_name") else self._resolve_division(division) if division else False
        gameday = gameday if hasattr(gameday, "_name") else self._resolve_gameday(gameday) if gameday else False
        planner_root = self._get_planner_root_gameday(gameday) if gameday else False
        presence_model = self._workspace_presence_model()
        presence = presence_model.search(
            [
                ("user_id", "=", self.env.user.id),
                ("competition_id", "=", competition.id),
            ],
            limit=1,
        )
        values = {
            "competition_id": competition.id,
            "division_id": division.id if division else gameday.tournament_id.id if gameday else False,
            "planner_root_round_id": planner_root.id if planner_root else False,
            "active_section": self._normalize_presence_section(active_section),
            "last_seen": fields.Datetime.now(),
        }
        if presence:
            presence.write(values)
        else:
            presence = presence_model.create(
                {
                    **values,
                    "user_id": self.env.user.id,
                }
            )
        return presence

    def _serialize_workspace_presence(self, presence, planner_root=False):
        return {
            "id": presence.id,
            "user_id": presence.user_id.id,
            "user_name": presence.user_id.display_name,
            "division_id": presence.division_id.id if presence.division_id else False,
            "division_name": presence.division_id.display_name if presence.division_id else False,
            "planner_root_id": presence.planner_root_round_id.id
            if presence.planner_root_round_id
            else False,
            "gameday_name": presence.planner_root_round_id.display_name
            if presence.planner_root_round_id
            else False,
            "active_section": presence.active_section,
            "last_seen": self._serialize_datetime(presence.last_seen),
            "is_current_user": presence.user_id == self.env.user,
            "is_same_gameday": bool(
                planner_root and presence.planner_root_round_id == planner_root
            ),
        }

    def _workspace_presence_summary(self, competition=False, division=False, gameday=False):
        competition = self._coerce_workspace_competition(
            competition=competition,
            division=division,
            gameday=gameday,
        )
        if not competition:
            return {
                "active_users": [],
                "same_gameday_users": [],
                "active_count": 0,
                "same_gameday_count": 0,
                "has_same_gameday_editors": False,
                "warning_message": False,
            }
        gameday = gameday if hasattr(gameday, "_name") else self._resolve_gameday(gameday) if gameday else False
        planner_root = self._get_planner_root_gameday(gameday) if gameday else False
        cutoff = fields.Datetime.to_string(fields.Datetime.now() - timedelta(minutes=5))
        presences = self._workspace_presence_model().search(
            [
                ("competition_id", "=", competition.id),
                ("last_seen", ">=", cutoff),
            ],
            order="last_seen desc, id desc",
        )
        active_users = [
            self._serialize_workspace_presence(presence, planner_root=planner_root)
            for presence in presences
        ]
        same_gameday_users = [
            user
            for user in active_users
            if user["planner_root_id"] == (planner_root.id if planner_root else False)
            and not user["is_current_user"]
        ]
        return {
            "active_users": active_users,
            "same_gameday_users": same_gameday_users,
            "active_count": len(active_users),
            "same_gameday_count": len(same_gameday_users),
            "has_same_gameday_editors": bool(same_gameday_users),
            "warning_message": _(
                "Another planner is currently active on this gameday. Coordinate before making force changes."
            )
            if same_gameday_users
            else False,
        }

    def _resolve_competition(self, competition_id):
        edition = self.env["federation.competition.edition"].browse(competition_id)
        if not edition.exists():
            raise ValidationError(_("The selected competition could not be found."))
        return edition

    def _resolve_competition_template(self, template_id):
        template = self.env["federation.competition"].browse(template_id)
        if not template.exists():
            raise ValidationError(
                _("The selected competition template could not be found.")
            )
        return template

    def _resolve_season(self, season_id):
        season = self.env["federation.season"].browse(season_id)
        if not season.exists():
            raise ValidationError(_("Select a valid season before creating a competition."))
        return season

    def _resolve_division(self, division_id, competition=False):
        division = self.env["federation.tournament"].browse(division_id)
        if not division.exists():
            raise ValidationError(_("The selected division could not be found."))
        if competition and division.edition_id != competition:
            raise ValidationError(
                _("The selected division does not belong to this competition.")
            )
        return division

    def _resolve_gameday(self, gameday_id):
        gameday = self.env["federation.tournament.round"].browse(gameday_id)
        if not gameday.exists():
            raise ValidationError(_("The selected gameday could not be found."))
        return gameday

    def _resolve_slot(self, slot_id):
        slot = self.env["federation.match.slot"].browse(slot_id)
        if not slot.exists():
            raise ValidationError(_("The selected slot could not be found."))
        return slot

    def _resolve_match(self, match_id):
        match = self.env["federation.match"].browse(match_id)
        if not match.exists():
            raise ValidationError(_("The selected match could not be found."))
        return match

    def _resolve_matches(self, match_ids):
        resolved_ids = []
        for match_id in match_ids or []:
            if not match_id:
                continue
            try:
                resolved_ids.append(int(match_id))
            except (TypeError, ValueError):
                raise ValidationError(_("One or more selected matches are invalid."))
        if not resolved_ids:
            return []
        matches = self.env["federation.match"].browse(resolved_ids).exists()
        if len(matches) != len(set(resolved_ids)):
            raise ValidationError(_("One or more selected matches could not be found."))
        match_by_id = {match.id: match for match in matches}
        return [match_by_id[match_id] for match_id in resolved_ids if match_id in match_by_id]

    def _get_planner_root_gameday(self, gameday):
        return gameday._competition_workspace_root_round()

    def _get_linked_gamedays(self, gameday):
        return self._get_planner_root_gameday(gameday)._competition_workspace_linked_rounds()

    def _get_gameday_divisions(self, gameday):
        return self._get_linked_gamedays(gameday).mapped("tournament_id")

    def _get_workspace_stages(self, division):
        stages = division.stage_ids
        default_stage = division._workspace_get_or_create_stage()
        if default_stage:
            stages |= default_stage
        knockout_stage = division._workspace_get_or_create_knockout_stage()
        if knockout_stage:
            stages |= knockout_stage
        return stages.sorted(lambda record: (record.sequence or 0, record.id))

    def _resolve_workspace_stage(self, division, stage_id=False, stage_type=False):
        stage_model = self.env["federation.tournament.stage"]
        if stage_id:
            stage = stage_model.browse(stage_id).exists()
            if not stage or stage.tournament_id != division:
                raise ValidationError(
                    _("The selected stage does not belong to this division.")
                )
            return stage
        if stage_type:
            stage = self._get_workspace_stages(division).filtered(
                lambda record: record.stage_type == stage_type
            )[:1]
            if stage:
                return stage
            if stage_type == "group":
                stage = division._workspace_get_or_create_stage()
                if stage and stage.stage_type == "group":
                    return stage
            if stage_type == "knockout":
                stage = division._workspace_get_or_create_knockout_stage()
                if stage and stage.stage_type == "knockout":
                    return stage
            raise ValidationError(
                _(
                    "%(division)s does not have a workspace stage for %(stage_type)s planning.",
                    division=division.display_name,
                    stage_type=stage_type,
                )
            )
        return division._workspace_get_or_create_stage()

    def _resolve_shared_divisions(self, division, division_ids):
        requested_ids = [int(division_id) for division_id in (division_ids or []) if division_id]
        if not requested_ids:
            return self.env["federation.tournament"]

        shared_divisions = self.env["federation.tournament"].browse(requested_ids).exists()
        if len(shared_divisions) != len(set(requested_ids)):
            raise ValidationError(_("One or more shared divisions could not be found."))
        if division in shared_divisions:
            raise ValidationError(_("Do not add the selected division twice to the same gameday."))
        if any(shared_division.edition_id != division.edition_id for shared_division in shared_divisions):
            raise ValidationError(
                _("Shared gamedays can only include divisions from the same competition.")
            )
        return shared_divisions.sorted(lambda record: (record.name or "", record.id))

    def _get_match_planner_round(self, gameday, match):
        linked_rounds = self._get_linked_gamedays(gameday)
        candidate_rounds = linked_rounds.filtered(
            lambda round_record: round_record.tournament_id == match.tournament_id
        )
        if match.stage_id:
            stage_match = candidate_rounds.filtered(
                lambda round_record: round_record.stage_id == match.stage_id
            )[:1]
            if stage_match:
                return stage_match
        return candidate_rounds[:1]

    def _get_division_gamedays(self, division):
        return division.round_ids.sorted(lambda record: (record.sequence, record.id))

    def _get_division_planner_roots(self, division):
        planner_roots = self.env["federation.tournament.round"]
        seen_root_ids = set()
        for gameday in self._get_division_gamedays(division):
            root_round = self._get_planner_root_gameday(gameday)
            if root_round.id in seen_root_ids:
                continue
            seen_root_ids.add(root_round.id)
            planner_roots |= root_round
        return planner_roots

    def _get_division_planner_slots(self, division):
        return self._get_division_planner_roots(division).mapped("slot_ids")

    def _get_open_planner_slots(self, gameday):
        planner_root = self._get_planner_root_gameday(gameday)
        return planner_root.slot_ids.filtered(
            lambda slot: not slot.match_id and slot.state in ("available", "reserved")
        ).sorted(
            lambda record: (
                record.start_datetime,
                record.playing_area_id.name or "",
                record.id,
            )
        )

    def _get_gameday_unscheduled_matches(self, gameday):
        matches = self.env["federation.match"]
        linked_rounds = self._get_linked_gamedays(gameday)
        for division in self._get_gameday_divisions(gameday):
            linked_round = linked_rounds.filtered(
                lambda round_record: round_record.tournament_id == division
            )[:1]
            matches |= self._get_unscheduled_matches(
                division,
                stage=linked_round.stage_id if linked_round else False,
            )
        return matches.sorted(
            lambda match: (
                match.stage_id.sequence if match.stage_id else 0,
                match.tournament_id.name or "",
                match.round_number or 0,
                match.id,
            )
        )

    def _serialize_division_option(self, division):
        return {
            "id": division.id,
            "name": division.display_name,
        }

    def _get_gameday_team_options(self, gameday):
        team_options = []
        seen_signatures = set()
        for division in self._get_gameday_divisions(gameday).sorted(
            lambda record: (record.name or "", record.id)
        ):
            participants = division.participant_ids.sorted(
                lambda participant: (participant.seed or 9999, participant.team_id.name or "")
            )
            for participant in participants:
                if not participant.team_id:
                    continue
                signature = (participant.team_id.id, division.id)
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                team_options.append(
                    {
                        "team_id": participant.team_id.id,
                        "team_name": participant.team_id.display_name,
                        "division_id": division.id,
                        "division_name": division.display_name,
                    }
                )
        return team_options

    def _serialize_stage_option(self, stage, division=False):
        division = division or stage.tournament_id
        stage_matches = division.match_ids.filtered(lambda match: match.stage_id == stage)
        scheduled_matches = stage_matches.filtered("slot_id")
        gamedays = division.round_ids.filtered(lambda round_record: round_record.stage_id == stage)
        return {
            "id": stage.id,
            "name": stage.display_name,
            "stage_type": stage.stage_type,
            "stage_type_label": self._get_state_label(stage, "stage_type", stage.stage_type),
            "sequence": stage.sequence,
            "match_count": len(stage_matches),
            "scheduled_match_count": len(scheduled_matches),
            "unscheduled_match_count": len(stage_matches - scheduled_matches),
            "gameday_count": len(gamedays),
            "is_workspace_stage": division.workspace_stage_id == stage,
            "is_knockout_stage": division.workspace_knockout_stage_id == stage,
        }

    def _normalize_time_value(self, value, field_label):
        if isinstance(value, time):
            return value
        if isinstance(value, (float, int)):
            total_minutes = int(round(float(value) * 60))
            hours, minutes = divmod(total_minutes, 60)
            return time(hour=hours % 24, minute=minutes)
        if isinstance(value, str):
            for fmt in ("%H:%M:%S", "%H:%M"):
                try:
                    return datetime.strptime(value, fmt).time()
                except ValueError:
                    continue
        raise ValidationError(
            _("%(field)s must use a valid time value.", field=field_label)
        )

    def _serialize_datetime(self, value):
        return fields.Datetime.to_string(value) if value else False

    def _serialize_date(self, value):
        return fields.Date.to_string(value) if value else False

    def _format_minutes_label(self, minutes):
        if minutes is False or minutes is None:
            return False
        total_minutes = int(round(minutes))
        hours, minute_value = divmod(total_minutes, 60)
        return f"{hours:02d}:{minute_value:02d}"

    def _fairness_score_component(self, key, label, gap_value, threshold):
        resolved_gap = max(gap_value or 0, 0)
        if threshold <= 0:
            score = 100 if not resolved_gap else 0
        else:
            score = max(
                0,
                round(100 - min(1, float(resolved_gap) / float(threshold)) * 100),
            )
        return {
            "key": key,
            "label": label,
            "gap_value": resolved_gap,
            "threshold": threshold,
            "score": score,
        }

    def _empty_fairness_summary(self):
        return {
            "tracked_team_count": 0,
            "scheduled_match_count": 0,
            "rest_balance_gap_minutes": 0,
            "court_balance_gap_percent": 0,
            "timeslot_balance_gap_minutes": 0,
            "warnings": [],
            "score_components": [
                self._fairness_score_component("rest_fairness", _("Rest fairness"), 0, 30),
                self._fairness_score_component("court_fairness", _("Court fairness"), 0, 50),
                self._fairness_score_component("timeslot_fairness", _("Timeslot fairness"), 0, 90),
            ],
            "team_metrics": [],
        }

    def _fairness_summary(self, division=False, matches=False):
        scheduled_matches = matches or (division.match_ids if division else self.env["federation.match"])
        scheduled_matches = scheduled_matches.filtered(
            lambda match: match.slot_id and match.slot_id.start_datetime and match.slot_id.end_datetime
        )
        if not scheduled_matches:
            return self._empty_fairness_summary()

        seed_by_team = {}
        if division:
            seed_by_team = {
                participant.team_id.id: participant.seed or 9999
                for participant in division.participant_ids.filtered("team_id")
            }

        team_windows = {}
        for match in scheduled_matches.sorted(
            lambda record: (record.slot_id.start_datetime, record.slot_id.id, record.id)
        ):
            for team in (match.home_team_id, match.away_team_id):
                if not team:
                    continue
                team_windows.setdefault(team.id, {"team": team, "windows": []})["windows"].append(
                    {
                        "start": match.slot_id.start_datetime,
                        "end": match.slot_id.end_datetime,
                        "court": match.slot_id.playing_area_id,
                        "match": match,
                    }
                )

        team_metrics = []
        average_rest_values = []
        average_start_values = []
        court_repeat_ratios = []
        for team_id, payload in sorted(
            team_windows.items(),
            key=lambda item: (
                seed_by_team.get(item[0], 9999),
                item[1]["team"].name or "",
                item[0],
            ),
        ):
            windows = sorted(payload["windows"], key=lambda item: (item["start"], item["match"].id))
            start_minutes = [window["start"].hour * 60 + window["start"].minute for window in windows]
            rest_gaps = [
                int((current["start"] - previous["end"]).total_seconds() / 60)
                for previous, current in zip(windows, windows[1:])
            ]
            average_rest_gap = (
                round(sum(rest_gaps) / len(rest_gaps)) if rest_gaps else False
            )
            min_rest_gap = min(rest_gaps) if rest_gaps else False
            average_start_minutes = (
                round(sum(start_minutes) / len(start_minutes)) if start_minutes else False
            )
            court_counts = {}
            for window in windows:
                court = window["court"]
                if not court:
                    continue
                court_counts[court.id] = {
                    "name": court.display_name,
                    "count": court_counts.get(court.id, {}).get("count", 0) + 1,
                }
            primary_court = (
                max(
                    court_counts.items(),
                    key=lambda item: (item[1]["count"], item[1]["name"], item[0]),
                )[1]
                if court_counts
                else False
            )
            court_repeat_ratio = (
                round(primary_court["count"] / len(windows), 2) if primary_court else 0
            )

            if average_rest_gap is not False:
                average_rest_values.append(average_rest_gap)
            if average_start_minutes is not False:
                average_start_values.append(average_start_minutes)
            if windows:
                court_repeat_ratios.append(court_repeat_ratio)

            team_metrics.append(
                {
                    "team_id": team_id,
                    "team_name": payload["team"].display_name,
                    "scheduled_match_count": len(windows),
                    "distinct_court_count": len(court_counts),
                    "primary_court_name": primary_court["name"] if primary_court else False,
                    "court_repeat_percent": int(round(court_repeat_ratio * 100)),
                    "average_start_minutes": average_start_minutes,
                    "average_start_label": self._format_minutes_label(average_start_minutes),
                    "earliest_start_label": self._format_minutes_label(min(start_minutes) if start_minutes else False),
                    "latest_start_label": self._format_minutes_label(max(start_minutes) if start_minutes else False),
                    "average_rest_gap_minutes": average_rest_gap,
                    "min_rest_gap_minutes": min_rest_gap,
                }
            )

        rest_balance_gap = (
            max(average_rest_values) - min(average_rest_values)
            if len(average_rest_values) > 1
            else 0
        )
        court_balance_gap_percent = (
            int(round((max(court_repeat_ratios) - min(court_repeat_ratios)) * 100))
            if len(court_repeat_ratios) > 1
            else 0
        )
        timeslot_balance_gap = (
            max(average_start_values) - min(average_start_values)
            if len(average_start_values) > 1
            else 0
        )

        rest_threshold = max(division.minimum_rest_minutes or 0, 30) if division else 30
        warnings = []
        if rest_balance_gap > rest_threshold:
            warnings.append(
                {
                    "code": "rest_balance",
                    "message": _(
                        "Average team rest gaps differ by %(minutes)s minutes.",
                        minutes=rest_balance_gap,
                    ),
                }
            )
        if court_balance_gap_percent > 50:
            warnings.append(
                {
                    "code": "court_balance",
                    "message": _(
                        "Court concentration differs by %(percent)s%% across teams.",
                        percent=court_balance_gap_percent,
                    ),
                }
            )
        if timeslot_balance_gap > 90:
            warnings.append(
                {
                    "code": "timeslot_balance",
                    "message": _(
                        "Average team start times differ by %(minutes)s minutes.",
                        minutes=timeslot_balance_gap,
                    ),
                }
            )

        return {
            "tracked_team_count": len(team_metrics),
            "scheduled_match_count": len(scheduled_matches),
            "rest_balance_gap_minutes": rest_balance_gap,
            "court_balance_gap_percent": court_balance_gap_percent,
            "timeslot_balance_gap_minutes": timeslot_balance_gap,
            "warnings": warnings,
            "score_components": [
                self._fairness_score_component(
                    "rest_fairness",
                    _("Rest fairness"),
                    rest_balance_gap,
                    rest_threshold,
                ),
                self._fairness_score_component(
                    "court_fairness",
                    _("Court fairness"),
                    court_balance_gap_percent,
                    50,
                ),
                self._fairness_score_component(
                    "timeslot_fairness",
                    _("Timeslot fairness"),
                    timeslot_balance_gap,
                    90,
                ),
            ],
            "team_metrics": team_metrics,
        }

    def _fairness_overview_summary(self, division_payloads):
        summaries = [
            payload.get("fairness_summary")
            for payload in division_payloads
            if payload.get("fairness_summary")
        ]
        if not summaries:
            return {
                **self._empty_fairness_summary(),
                "tracked_division_count": 0,
                "warning_division_count": 0,
                "division_metrics": [],
            }

        score_values = {}
        for summary in summaries:
            for component in summary.get("score_components") or []:
                score_values.setdefault(component["key"], []).append(component["score"])

        return {
            "tracked_team_count": sum(summary["tracked_team_count"] for summary in summaries),
            "scheduled_match_count": sum(summary["scheduled_match_count"] for summary in summaries),
            "rest_balance_gap_minutes": max(
                summary["rest_balance_gap_minutes"] for summary in summaries
            ),
            "court_balance_gap_percent": max(
                summary["court_balance_gap_percent"] for summary in summaries
            ),
            "timeslot_balance_gap_minutes": max(
                summary["timeslot_balance_gap_minutes"] for summary in summaries
            ),
            "warnings": [
                warning
                for summary in summaries
                for warning in (summary.get("warnings") or [])
            ],
            "score_components": [
                {
                    "key": key,
                    "label": key.replace("_", " ").title(),
                    "score": round(sum(values) / len(values)) if values else 100,
                }
                for key, values in sorted(score_values.items())
            ],
            "team_metrics": [],
            "tracked_division_count": len(summaries),
            "warning_division_count": sum(
                1 for summary in summaries if summary.get("warnings")
            ),
            "division_metrics": [
                {
                    "division_id": payload["id"],
                    "division_name": payload["name"],
                    "rest_balance_gap_minutes": payload["fairness_summary"]["rest_balance_gap_minutes"],
                    "court_balance_gap_percent": payload["fairness_summary"]["court_balance_gap_percent"],
                    "timeslot_balance_gap_minutes": payload["fairness_summary"]["timeslot_balance_gap_minutes"],
                    "warning_count": len(payload["fairness_summary"].get("warnings") or []),
                }
                for payload in division_payloads
            ],
        }

    def _get_state_label(self, record, field_name, value):
        field = record._fields.get(field_name)
        if not field or not field.selection:
            return value
        return dict(field.selection).get(value, value)

    def _get_entry_status_key(self, participant):
        return "submitted" if participant.state == "registered" else participant.state

    def _get_unscheduled_matches_for_stage(self, division, stage=False):
        stages = stage or self._get_workspace_stages(division)
        stage_ids = {stages.id} if len(stages) == 1 else set(stages.ids)
        if not stage_ids:
            return self.env["federation.match"]
        return division.match_ids.filtered(
            lambda match: match.stage_id.id in stage_ids
            and not match.slot_id
            and match.state not in ("cancelled", "done", "in_progress")
        ).sorted(
            lambda match: (
                match.stage_id.sequence if match.stage_id else 0,
                match.round_number or 0,
                match.id,
            )
        )

    def _get_unscheduled_matches(self, division, stage=False):
        return self._get_unscheduled_matches_for_stage(division, stage=stage)

    def _serialize_team_entry(self, participant):
        status_key = self._get_entry_status_key(participant)
        status_labels = {
            "draft": _("Draft"),
            "submitted": _("Submitted"),
            "confirmed": _("Confirmed"),
            "withdrawn": _("Withdrawn"),
        }
        return {
            "id": participant.id,
            "team_id": participant.team_id.id,
            "team_name": participant.team_id.display_name,
            "club_name": participant.club_id.display_name if participant.club_id else False,
            "seed": participant.seed,
            "status": status_key,
            "status_label": status_labels.get(status_key, status_key),
        }

    def _get_match_side_label(self, match, side):
        if side == "home":
            team = match.home_team_id
            source_match = match.source_match_1_id
            source_type = match.source_type_1
        else:
            team = match.away_team_id
            source_match = match.source_match_2_id
            source_type = match.source_type_2

        if team:
            return team.display_name
        if source_match:
            source_label = _("Winner") if source_type != "loser" else _("Loser")
            return _(
                "%(source)s of %(match)s",
                source=source_label,
                match=source_match.display_name,
            )
        return _("TBD")

    def _serialize_match_card(self, match):
        home_team_name = self._get_match_side_label(match, "home")
        away_team_name = self._get_match_side_label(match, "away")
        payload = {
            "id": match.id,
            "name": _(
                "%(home)s vs %(away)s",
                home=home_team_name,
                away=away_team_name,
            ),
            "home_team_id": match.home_team_id.id,
            "home_team_name": home_team_name,
            "away_team_id": match.away_team_id.id,
            "away_team_name": away_team_name,
            "round_number": match.round_number,
            "bracket_position": getattr(match, "bracket_position", 0),
            "state": match.state,
            "state_label": self._get_state_label(match, "state", match.state),
            "result_state": getattr(match, "result_state", False),
            "result_state_label": self._get_state_label(
                match,
                "result_state",
                getattr(match, "result_state", False),
            )
            if "result_state" in match._fields
            else False,
            "division_id": match.tournament_id.id,
            "division_name": match.tournament_id.display_name,
            "stage_id": match.stage_id.id if match.stage_id else False,
            "stage_name": match.stage_id.display_name if match.stage_id else False,
            "stage_type": match.stage_id.stage_type if match.stage_id else False,
            "slot_id": match.slot_id.id if match.slot_id else False,
            "scheduled_start": self._serialize_datetime(match.date_scheduled),
            "court_name": match.playing_area_id.display_name
            if "playing_area_id" in match._fields and match.playing_area_id
            else False,
            "group_id": match.group_id.id if match.group_id else False,
            "group_name": match.group_id.display_name if match.group_id else False,
        }
        return self._merge_workspace_payload(
            payload,
            self._workspace_extension_payload(
                "extend_match_card",
                match,
                payload=payload,
            ),
        )

    def _slot_summary(self, slot):
        if not slot:
            return _("No slot")
        start_label = (
            fields.Datetime.to_datetime(slot.start_datetime).strftime("%H:%M")
            if slot.start_datetime
            else _("No time")
        )
        return _(
            "%(court)s at %(start)s",
            court=slot.playing_area_id.display_name or slot.display_name,
            start=start_label,
        )

    def _serialize_planner_operation(self, operation):
        operation_label = self._get_state_label(
            operation, "operation_type", operation.operation_type
        )
        state_label = self._get_state_label(operation, "state", operation.state)
        if operation.operation_type == "assign":
            summary = _(
                "Assigned %(match)s to %(slot)s",
                match=operation.match_id.display_name,
                slot=self._slot_summary(operation.new_slot_id),
            )
        elif operation.operation_type == "move":
            summary = _(
                "Moved %(match)s from %(old_slot)s to %(new_slot)s",
                match=operation.match_id.display_name,
                old_slot=self._slot_summary(operation.old_slot_id),
                new_slot=self._slot_summary(operation.new_slot_id),
            )
        else:
            summary = _(
                "Unassigned %(match)s from %(slot)s",
                match=operation.match_id.display_name,
                slot=self._slot_summary(operation.old_slot_id),
            )
        if operation.forced:
            summary = _(
                "%(summary)s after manager warning override",
                summary=summary,
            )
        return {
            "id": operation.id,
            "operation_type": operation.operation_type,
            "operation_type_label": operation_label,
            "state": operation.state,
            "state_label": state_label,
            "summary": summary,
            "user_name": operation.user_id.display_name,
            "forced": operation.forced,
            "override_reason": operation.override_reason or False,
            "batch_key": operation.batch_key or False,
            "created_at": self._serialize_datetime(operation.create_date),
            "created_at_label": fields.Datetime.to_datetime(
                operation.create_date
            ).strftime("%Y-%m-%d %H:%M")
            if operation.create_date
            else False,
        }

    def _serialize_planner_operation_history(self, gameday, limit=12):
        planner_root = self._get_planner_root_gameday(gameday)
        operations = self._planner_operation_model().search(
            [("planner_root_round_id", "=", planner_root.id)],
            order="id desc",
            limit=limit,
        )
        return [self._serialize_planner_operation(operation) for operation in operations]

    def _can_undo_planner_operations(self, gameday):
        planner_root = self._get_planner_root_gameday(gameday)
        return bool(
            self._planner_operation_model().search(
                [
                    ("planner_root_round_id", "=", planner_root.id),
                    ("state", "=", "applied"),
                ],
                limit=1,
            )
        )

    def _can_redo_planner_operations(self, gameday):
        planner_root = self._get_planner_root_gameday(gameday)
        return bool(
            self._planner_operation_model().search(
                [
                    ("planner_root_round_id", "=", planner_root.id),
                    ("state", "=", "undone"),
                ],
                limit=1,
            )
        )

    def _get_generation_action_label(self, division):
        return {
            "single_round_robin": _("Generate round robin"),
            "double_round_robin": _("Generate double round robin"),
            "knockout": _("Generate knockout bracket"),
            "pool_then_bracket": self._pool_then_bracket_action_label(division),
        }.get(division.planning_format, False)

    def _get_generation_description(self, division):
        return {
            "single_round_robin": _(
                "Creates one full cycle of unscheduled league matches that can be assigned later in the planner."
            ),
            "double_round_robin": _(
                "Creates home-and-away league fixtures while keeping gameday and slot assignment separate."
            ),
            "knockout": _(
                "Creates an unscheduled seeded bracket with byes and advancement links while preserving planner assignment for later."
            ),
            "manual": _(
                "Manual mode keeps match creation outside the guided generator."
            ),
            "pool_then_bracket": self._pool_then_bracket_description(division),
        }.get(division.planning_format, _("Generate the schedule structure for this division."))

    def _get_generation_empty_message(self, division):
        return {
            "single_round_robin": _(
                "Generate a round robin schedule to preview the rounds here."
            ),
            "double_round_robin": _(
                "Generate a double round robin schedule to preview the home-and-away rounds here."
            ),
            "knockout": _(
                "Generate a knockout bracket to preview the seeded rounds here."
            ),
            "manual": _(
                "Create matches manually or switch to a generated planning format."
            ),
            "pool_then_bracket": self._pool_then_bracket_empty_message(division),
        }.get(division.planning_format, _("No generated preview is available yet."))

    def _pool_then_bracket_generation_phase(self, division):
        pool_stage = division._workspace_get_or_create_stage()
        knockout_stage = division._workspace_get_or_create_knockout_stage()
        pool_matches = division.match_ids.filtered(lambda match: match.stage_id == pool_stage)
        knockout_matches = division.match_ids.filtered(
            lambda match: match.stage_id == knockout_stage
        )
        qualified_participants = division.participant_ids.filtered(
            lambda participant: participant.state == "confirmed"
            and participant.stage_id == knockout_stage
        )
        if not pool_matches:
            return "pool_phase"
        if not knockout_matches and qualified_participants:
            return "bracket_phase"
        if not knockout_matches:
            return "waiting_for_progression"
        return "complete"

    def _pool_then_bracket_action_label(self, division):
        return {
            "pool_phase": _("Generate pool phase"),
            "bracket_phase": _("Generate knockout bracket"),
        }.get(self._pool_then_bracket_generation_phase(division), False)

    def _pool_then_bracket_description(self, division):
        return {
            "pool_phase": _(
                "Creates balanced pools, round-robin matches inside each pool, and the knockout progression rules that advance qualifiers later."
            ),
            "bracket_phase": _(
                "Creates the seeded knockout bracket from teams that already advanced out of the pool phase."
            ),
            "waiting_for_progression": _(
                "Pool matches are ready. Freeze each pool standing to auto-advance qualified teams before generating the knockout bracket."
            ),
            "complete": _(
                "Pool matches, progression rules, and the knockout bracket have already been generated for this division."
            ),
        }[self._pool_then_bracket_generation_phase(division)]

    def _pool_then_bracket_empty_message(self, division):
        return {
            "pool_phase": _(
                "Generate the pool phase to seed the division into balanced groups."
            ),
            "bracket_phase": _(
                "Qualified teams are ready. Generate the knockout bracket to continue planning the elimination stage."
            ),
            "waiting_for_progression": _(
                "Pool standings must be frozen before bracket qualifiers can advance automatically."
            ),
            "complete": _(
                "Both pool and knockout structures are already available in this workspace."
            ),
        }[self._pool_then_bracket_generation_phase(division)]

    def _serialize_round_preview(self, division):
        grouped = {}
        knockout_round_names = {}
        for stage in self._get_workspace_stages(division):
            round_matches = division.match_ids.filtered(
                lambda record, stage=stage: record.round_number and record.stage_id == stage
            )
            if stage.stage_type == "knockout" and round_matches:
                knockout_round_names[stage.id] = self.env[
                    "federation.knockout.service"
                ]._get_round_names(max(round_matches.mapped("round_number") or [1]))
            for match in round_matches:
                grouped.setdefault((stage.id, match.round_number), []).append(
                    self._serialize_match_card(match)
                )
        return [
            {
                "stage_id": stage_id,
                "stage_name": self.env["federation.tournament.stage"].browse(stage_id).display_name,
                "stage_type": self.env["federation.tournament.stage"].browse(stage_id).stage_type,
                "round_number": round_number,
                "name": knockout_round_names.get(stage_id, {}).get(
                    round_number,
                    _("Round %(number)s", number=round_number),
                ),
                "matches": sorted(
                    matches,
                    key=lambda item: (item.get("bracket_position") or 0, item["id"]),
                ),
            }
            for (stage_id, round_number), matches in sorted(
                grouped.items(),
                key=lambda item: (
                    self.env["federation.tournament.stage"].browse(item[0][0]).sequence or 0,
                    item[0][1],
                    item[0][0],
                ),
            )
        ]

    def _serialize_generation_preview(self, division):
        rounds = self._serialize_round_preview(division)
        return {
            "format": division.planning_format,
            "format_label": self._get_state_label(
                division, "planning_format", division.planning_format
            ),
            "action_label": self._get_generation_action_label(division),
            "description": self._get_generation_description(division),
            "empty_message": self._get_generation_empty_message(division),
            "supported": division.planning_format
            in (
                "single_round_robin",
                "double_round_robin",
                "knockout",
                "pool_then_bracket",
            ),
            "rounds": rounds,
        }

    def _serialize_gameday(self, gameday):
        planner_root = self._get_planner_root_gameday(gameday)
        assigned_matches = planner_root.slot_ids.filtered("match_id")
        participating_divisions = self._get_gameday_divisions(planner_root).sorted(
            lambda record: (record.name or "", record.id)
        )
        payload = {
            "id": gameday.id,
            "planner_root_id": planner_root.id,
            "name": gameday.name,
            "date": self._serialize_date(gameday.round_date),
            "stage_id": gameday.stage_id.id if gameday.stage_id else False,
            "stage_name": gameday.stage_id.display_name if gameday.stage_id else False,
            "stage_type": gameday.stage_id.stage_type if gameday.stage_id else False,
            "planner_state": planner_root.planner_state,
            "planner_state_label": self._get_state_label(
                planner_root, "planner_state", planner_root.planner_state
            ),
            "planner_revision": planner_root.planner_revision,
            "venue_id": planner_root.venue_id.id
            if "venue_id" in planner_root._fields and planner_root.venue_id
            else False,
            "venue_name": planner_root.venue_id.display_name
            if "venue_id" in planner_root._fields and planner_root.venue_id
            else False,
            "slot_count": len(planner_root.slot_ids),
            "assigned_count": len(assigned_matches),
            "empty_slot_count": len(planner_root.slot_ids.filtered(lambda slot: not slot.match_id)),
            "publish_locked": planner_root.publish_locked,
            "schedule_revisions": self._serialize_schedule_revision_summary(planner_root),
            "is_shared": len(participating_divisions) > 1,
            "participating_divisions": [
                self._serialize_division_option(division)
                for division in participating_divisions
            ],
        }
        return self._merge_workspace_payload(
            payload,
            self._workspace_extension_payload(
                "extend_gameday_payload",
                gameday,
                payload=payload,
            ),
        )

    def _serialize_division(self, division):
        unscheduled_matches = self._get_unscheduled_matches(division)
        planner_slots = self._get_division_planner_slots(division)
        gamedays = self._get_division_gamedays(division)
        fairness_summary = self._fairness_summary(division=division)
        payload = {
            "id": division.id,
            "name": division.name,
            "competition_id": division.edition_id.id if division.edition_id else False,
            "workspace_state": division.workspace_state,
            "workspace_state_label": self._get_state_label(
                division, "workspace_state", division.workspace_state
            ),
            "planning_format": division.planning_format,
            "planning_format_label": self._get_state_label(
                division, "planning_format", division.planning_format
            ),
            "entries_locked": division.entries_locked,
            "minimum_rest_minutes": division.minimum_rest_minutes,
            "max_consecutive_matches_per_team": division.max_consecutive_matches_per_team,
            "pool_count": division.pool_count,
            "pool_qualifier_count": division.pool_qualifier_count,
            "participant_count": len(division.participant_ids),
            "confirmed_participant_count": len(
                division.participant_ids.filtered(lambda participant: participant.state == "confirmed")
            ),
            "match_count": len(division.match_ids),
            "scheduled_match_count": len(division.match_ids.filtered("slot_id")),
            "unscheduled_match_count": len(unscheduled_matches),
            "gameday_count": len(gamedays),
            "slot_count": len(planner_slots),
            "fairness_summary": fairness_summary,
            "stage_options": [
                self._serialize_stage_option(stage, division=division)
                for stage in self._get_workspace_stages(division)
            ],
            "workspace_stage_id": division.workspace_stage_id.id if division.workspace_stage_id else False,
            "workspace_knockout_stage_id": division.workspace_knockout_stage_id.id
            if division.workspace_knockout_stage_id
            else False,
            "generation_action_label": self._get_generation_action_label(division),
            "guided_generation_supported": division.planning_format
            in (
                "single_round_robin",
                "double_round_robin",
                "knockout",
                "pool_then_bracket",
            ),
            "next_action": self._get_next_action(division),
        }
        return self._merge_workspace_payload(
            payload,
            self._workspace_extension_payload(
                "extend_division_payload",
                division,
                payload=payload,
            ),
        )

    def _get_next_action(self, division):
        confirmed_count = len(
            division.participant_ids.filtered(lambda participant: participant.state == "confirmed")
        )
        if not division.id:
            return _("Create the first division.")
        if confirmed_count < 2:
            return _("Confirm at least two team entries.")
        if not division.entries_locked:
            return _("Lock the participant list.")
        if not division.match_ids.filtered(
            lambda match: match.stage_id == division._workspace_get_or_create_stage()
        ):
            return {
                "single_round_robin": _("Generate the round-robin rounds."),
                "double_round_robin": _("Generate the double round-robin rounds."),
                "knockout": _("Generate the knockout bracket."),
                "manual": _("Create the competition matches manually."),
                "pool_then_bracket": _("Generate the pool phase."),
            }.get(
                division.planning_format,
                _("Generate the schedule structure."),
            )
        if (
            division.planning_format == "pool_then_bracket"
            and self._pool_then_bracket_generation_phase(division) == "bracket_phase"
        ):
            return _("Generate the knockout bracket.")
        if (
            division.planning_format == "pool_then_bracket"
            and self._pool_then_bracket_generation_phase(division)
            == "waiting_for_progression"
        ):
            return _("Freeze pool standings to auto-advance the knockout qualifiers.")
        if not self._get_division_gamedays(division):
            return _("Create the first gameday.")
        if not self._get_division_planner_slots(division):
            return _("Generate court and timeslot slots.")
        validation = self._validate_division_schedule(division)
        if validation["blocking"]:
            return _("Resolve blocking planner conflicts.")
        if validation["unscheduled_matches"]:
            return _("Assign the remaining unscheduled matches.")
        if division.workspace_state != "published":
            return _("Validate and publish the schedule.")
        if any(
            planner_root.schedule_draft_revision_id
            for planner_root in self._get_division_planner_roots(division)
        ):
            return _("Review the current draft revision and republish when ready.")
        return _("Maintain the published schedule.")

    def _get_workspace_overview(self, competition, divisions):
        division_payloads = [self._serialize_division(division) for division in divisions]
        selected_payload = division_payloads[0] if division_payloads else {}
        validation = (
            self.validate_competition_schedule(competition.id)
            if competition and divisions
            else self.validate_competition_schedule(division_id=divisions[:1].id)
            if divisions
            else {"blocking": [], "warnings": [], "unscheduled_matches": [], "empty_slots": []}
        )
        payload = {
            "competition_name": competition.name if competition else selected_payload.get("name"),
            "competition_state": competition.state if competition else False,
            "competition_state_label": self._get_state_label(
                competition,
                "state",
                competition.state,
            )
            if competition
            else False,
            "division_count": len(divisions),
            "team_count": sum(payload["confirmed_participant_count"] for payload in division_payloads),
            "match_count": sum(payload["match_count"] for payload in division_payloads),
            "scheduled_count": sum(payload["scheduled_match_count"] for payload in division_payloads),
            "unscheduled_count": sum(payload["unscheduled_match_count"] for payload in division_payloads),
            "conflict_count": len(validation["blocking"]),
            "warning_count": len(validation["warnings"]),
            "fairness_summary": self._fairness_overview_summary(division_payloads),
            "next_action": (
                selected_payload.get("next_action")
                if selected_payload
                else _("Create the competition to begin planning.")
            ),
        }
        return self._merge_workspace_payload(
            payload,
            self._workspace_extension_payload(
                "extend_overview_payload",
                competition,
                divisions,
                payload=payload,
            ),
        )

    def _ensure_manager_for_create(self):
        capabilities = self._check_access(require_publish=True)
        if not capabilities["is_manager"]:
            raise AccessError(
                _("Only federation managers can create competitions from the workspace.")
            )
        return capabilities

    @api.model
    def create_competition_shell(self, vals):
        self._ensure_manager_for_create()
        name = (vals.get("name") or "").strip()
        if not name:
            raise ValidationError(_("Provide a name for the competition."))
        season_id = vals.get("season_id")
        if not season_id:
            raise ValidationError(_("Select a season before creating a competition."))
        season = self._resolve_season(season_id)
        competition_vals = vals.get("competition_vals") or {}
        competition_id = vals.get("competition_id")
        if competition_id:
            competition_id = self._resolve_competition_template(competition_id).id
        else:
            if not competition_vals.get("name"):
                raise ValidationError(
                    _(
                        "Provide a competition template or a template name to create the competition."
                    )
                )
            competition = self.env["federation.competition"].create(
                {
                    "name": competition_vals["name"],
                    "code": competition_vals.get("code"),
                    "competition_type": competition_vals.get(
                        "competition_type", "league"
                    ),
                    "rule_set_id": competition_vals.get("rule_set_id"),
                }
            )
            competition_id = competition.id

        existing_edition = self.env["federation.competition.edition"].search(
            [
                ("competition_id", "=", competition_id),
                ("season_id", "=", season.id),
            ],
            limit=1,
        )
        if existing_edition:
            return {
                "competition_id": existing_edition.id,
                "created": False,
                "payload": self.get_competition_workspace_data(existing_edition.id),
            }

        edition = self.env["federation.competition.edition"].create(
            {
                "name": name,
                "competition_id": competition_id,
                "season_id": season.id,
                "date_start": vals.get("date_start"),
                "date_end": vals.get("date_end"),
                "rule_set_id": vals.get("rule_set_id"),
                "state": vals.get("state", "draft"),
            }
        )
        return {
            "competition_id": edition.id,
            "created": True,
            "payload": self.get_competition_workspace_data(edition.id),
        }

    @api.model
    def create_division(self, competition_id, vals):
        self._check_access()
        competition = self._resolve_competition(competition_id)
        division = self.env["federation.tournament"].create(
            {
                "name": vals["name"],
                "edition_id": competition.id,
                "competition_id": competition.competition_id.id,
                "season_id": competition.season_id.id,
                "date_start": vals.get("date_start") or competition.date_start,
                "date_end": vals.get("date_end") or competition.date_end,
                "state": vals.get("state", "draft"),
                "planning_format": vals.get("planning_format", "single_round_robin"),
                "workspace_state": "registration_open",
                "rule_set_id": vals.get("rule_set_id") or competition.rule_set_id.id,
                "category": vals.get("category"),
                "gender": vals.get("gender"),
                "location": vals.get("location"),
                "tournament_type": vals.get("tournament_type", "single_day"),
                "minimum_rest_minutes": vals.get("minimum_rest_minutes", 30),
                "max_consecutive_matches_per_team": vals.get(
                    "max_consecutive_matches_per_team", 1
                ),
                "pool_count": vals.get("pool_count", 2),
                "pool_qualifier_count": vals.get("pool_qualifier_count", 2),
            }
        )
        return {
            "division_id": division.id,
            "payload": self.get_competition_workspace_data(competition.id, division.id),
        }

    @api.model
    def update_division_planning_rules(self, division_id, vals):
        self._check_access()
        division = self._resolve_division(division_id)
        updates = {}
        if "minimum_rest_minutes" in vals:
            updates["minimum_rest_minutes"] = max(
                int(vals.get("minimum_rest_minutes") or 0),
                0,
            )
        if "max_consecutive_matches_per_team" in vals:
            updates["max_consecutive_matches_per_team"] = max(
                int(vals.get("max_consecutive_matches_per_team") or 1),
                1,
            )
        if not updates:
            raise ValidationError(_("Provide at least one planning rule to update."))
        division.write(updates)
        return {
            "payload": self.get_competition_workspace_data(
                division.edition_id.id if division.edition_id else False,
                division.id,
            )
        }

    @api.model
    def create_team_entry(self, division_id, vals):
        self._check_access()
        division = self._resolve_division(division_id)
        participant = self.env["federation.tournament.participant"].create(
            {
                "tournament_id": division.id,
                "team_id": vals["team_id"],
                "seed": vals.get("seed"),
                "state": vals.get("state", "registered"),
            }
        )
        if division.workspace_state == "draft":
            division._competition_workspace_transition_state("registration_open")
        return {
            "entry_id": participant.id,
            "payload": self.get_competition_workspace_data(
                division.edition_id.id if division.edition_id else False,
                division.id,
            ),
        }

    @api.model
    def confirm_team_entry(self, entry_id):
        self._check_access()
        participant = self.env["federation.tournament.participant"].browse(entry_id)
        if not participant.exists():
            raise ValidationError(_("The selected team entry could not be found."))
        participant.action_confirm()
        division = participant.tournament_id
        if division.workspace_state == "draft":
            division._competition_workspace_transition_state("registration_open")
        return {
            "payload": self.get_competition_workspace_data(
                division.edition_id.id if division.edition_id else False,
                division.id,
            )
        }

    @api.model
    def lock_team_entries(self, competition_id=False, division_id=False):
        self._check_access()
        if division_id:
            divisions = self._resolve_division(division_id)
        elif competition_id:
            divisions = self._resolve_competition(competition_id).tournament_ids
        else:
            raise ValidationError(_("Select a competition or division to lock entries."))
        divisions.action_lock_team_entries()
        target_division = divisions[:1]
        return {
            "payload": self.get_competition_workspace_data(
                competition_id or target_division.edition_id.id,
                target_division.id,
            )
        }

    def _get_generation_participants(self, division):
        return division.participant_ids.filtered(
            lambda participant: participant.state == "confirmed"
        ).sorted(lambda participant: (participant.seed or 9999, participant.team_id.name or ""))

    def _prepare_generation(self, division, force=False):
        if not division.entries_locked:
            raise ValidationError(
                _("Lock the participant list before generating competition matches.")
            )

        stage = division._workspace_get_or_create_stage()
        participants = self._get_generation_participants(division)
        if len(participants) < 2:
            raise ValidationError(
                _("At least two confirmed teams are required to generate rounds.")
            )

        stage_matches = division.match_ids.filtered(lambda match: match.stage_id == stage)
        if stage_matches:
            if not force:
                raise ValidationError(
                    _(
                        "Existing generated matches already exist for this division. Use force regeneration only when it is safe."
                    )
                )
            if stage_matches.filtered(
                lambda match: match.slot_id or match.state in ("in_progress", "done")
            ):
                raise ValidationError(
                    _("Assigned or completed matches cannot be regenerated safely.")
                )
            stage_matches.unlink()

        participants.write({"stage_id": stage.id, "group_id": False})
        return stage, participants

    def _generate_round_robin_matches(
        self, division, stage, participants, double_round=False
    ):
        pairings = self.env["federation.round.robin.service"]._generate_pairings(
            participants.mapped("team_id"),
            double_round,
        )
        Match = self.env["federation.match"]
        created_matches = Match.browse([])
        for round_number, round_pairings in enumerate(pairings, start=1):
            for home_team, away_team in round_pairings:
                if not home_team or not away_team:
                    continue
                created_matches |= Match.create(
                    {
                        "tournament_id": division.id,
                        "stage_id": stage.id,
                        "home_team_id": home_team.id,
                        "away_team_id": away_team.id,
                        "round_number": round_number,
                        "state": "draft",
                    }
                )
        return created_matches

    def _pool_then_bracket_order(self, pool_count):
        forward = list(range(pool_count))
        return forward + list(reversed(forward))

    def _pool_then_bracket_group_name(self, index):
        return _("Pool %(name)s", name=chr(65 + index))

    def _assign_pool_then_bracket_groups(self, division, stage, participants):
        pool_count = division.pool_count
        if len(participants) < pool_count:
            raise ValidationError(
                _(
                    "Pool Then Bracket needs at least %(count)s confirmed teams to fill %(pools)s pools.",
                    count=pool_count,
                    pools=pool_count,
                )
            )

        existing_groups = stage.group_ids.sorted(lambda group: (group.sequence, group.id))
        if len(existing_groups) < pool_count:
            for index in range(len(existing_groups), pool_count):
                existing_groups |= self.env["federation.tournament.group"].create(
                    {
                        "name": self._pool_then_bracket_group_name(index),
                        "stage_id": stage.id,
                        "sequence": (index + 1) * 10,
                        "max_participants": 0,
                    }
                )
        groups = existing_groups.sorted(lambda group: (group.sequence, group.id))[:pool_count]

        order = self._pool_then_bracket_order(pool_count)
        buckets = {group.id: self.env["federation.tournament.participant"] for group in groups}
        for index, participant in enumerate(participants):
            group = groups[order[index % len(order)]]
            buckets[group.id] |= participant

        for group in groups:
            group.write({"max_participants": len(buckets[group.id])})
            for participant in buckets[group.id].sorted(
                lambda record: (record.seed or 9999, record.team_id.name or "", record.id)
            ):
                participant.write(
                    {
                        "stage_id": stage.id,
                        "group_id": group.id,
                    }
                )
        return groups

    def _generate_group_round_robin_matches(self, division, stage, groups):
        Match = self.env["federation.match"]
        created_matches = Match.browse([])
        round_robin_service = self.env["federation.round.robin.service"]
        for group in groups.sorted(lambda record: (record.sequence, record.id)):
            group_participants = group.participant_ids.filtered(
                lambda participant: participant.state == "confirmed"
            ).sorted(lambda participant: (participant.seed or 9999, participant.team_id.name or ""))
            pairings = round_robin_service._generate_pairings(
                group_participants.mapped("team_id"),
                False,
            )
            for round_number, round_pairings in enumerate(pairings, start=1):
                for home_team, away_team in round_pairings:
                    if not home_team or not away_team:
                        continue
                    created_matches |= Match.create(
                        {
                            "tournament_id": division.id,
                            "stage_id": stage.id,
                            "group_id": group.id,
                            "home_team_id": home_team.id,
                            "away_team_id": away_team.id,
                            "round_number": round_number,
                            "state": "draft",
                        }
                    )
        return created_matches

    def _pool_then_bracket_seed_groups(self, knockout_stage, qualifier_count, pool_count):
        existing_groups = knockout_stage.group_ids.sorted(
            lambda group: (group.sequence, group.id)
        )
        while len(existing_groups) < qualifier_count:
            rank = len(existing_groups) + 1
            existing_groups |= self.env["federation.tournament.group"].create(
                {
                    "name": _("Qualifier Rank %(rank)s", rank=rank),
                    "stage_id": knockout_stage.id,
                    "sequence": rank * 10,
                    "max_participants": pool_count,
                }
            )
        return existing_groups.sorted(lambda group: (group.sequence, group.id))[
            :qualifier_count
        ]

    def _ensure_pool_then_bracket_progressions(
        self, division, pool_stage, knockout_stage, groups
    ):
        Progression = self.env["federation.stage.progression"]
        qualifier_groups = self._pool_then_bracket_seed_groups(
            knockout_stage,
            division.pool_qualifier_count,
            len(groups),
        )
        created = Progression.browse([])
        sequence = self._pool_bracket_progression_sequence_gap
        for qualifier_rank, qualifier_group in enumerate(qualifier_groups, start=1):
            for group in groups.sorted(lambda record: (record.sequence, record.id)):
                progression = Progression.search(
                    [
                        ("tournament_id", "=", division.id),
                        ("source_stage_id", "=", pool_stage.id),
                        ("source_group_id", "=", group.id),
                        ("target_stage_id", "=", knockout_stage.id),
                        ("target_group_id", "=", qualifier_group.id),
                        ("rank_from", "=", qualifier_rank),
                        ("rank_to", "=", qualifier_rank),
                    ],
                    limit=1,
                )
                if not progression:
                    progression = Progression.create(
                        {
                            "tournament_id": division.id,
                            "sequence": sequence,
                            "source_stage_id": pool_stage.id,
                            "source_group_id": group.id,
                            "target_stage_id": knockout_stage.id,
                            "target_group_id": qualifier_group.id,
                            "rank_from": qualifier_rank,
                            "rank_to": qualifier_rank,
                            "seeding_method": "keep_rank",
                            "auto_advance": True,
                        }
                    )
                created |= progression
                sequence += self._pool_bracket_progression_sequence_gap
        return created

    def _prepare_pool_then_bracket_knockout_participants(self, division, knockout_stage):
        participants = division.participant_ids.filtered(
            lambda participant: participant.state == "confirmed"
            and participant.stage_id == knockout_stage
        )
        ordered = participants.sorted(
            lambda participant: (
                participant.group_id.sequence if participant.group_id else 9999,
                participant.seed or 9999,
                participant.team_id.name or "",
                participant.id,
            )
        )
        for index, participant in enumerate(ordered, start=1):
            if participant.seed != index:
                participant.seed = index
        return ordered

    def _generate_pool_then_bracket_matches(self, division, force=False):
        if not division.entries_locked:
            raise ValidationError(
                _("Lock the participant list before generating competition matches.")
            )

        pool_stage = division._workspace_get_or_create_stage()
        knockout_stage = division._workspace_get_or_create_knockout_stage()
        participants = self._get_generation_participants(division)
        if len(participants) < 2:
            raise ValidationError(
                _("At least two confirmed teams are required to generate rounds.")
            )

        pool_matches = division.match_ids.filtered(lambda match: match.stage_id == pool_stage)
        knockout_matches = division.match_ids.filtered(
            lambda match: match.stage_id == knockout_stage
        )

        if force and (pool_matches or knockout_matches):
            generated_matches = pool_matches | knockout_matches
            if generated_matches.filtered(
                lambda match: match.slot_id or match.state in ("in_progress", "done")
            ):
                raise ValidationError(
                    _(
                        "Assigned or completed Pool Then Bracket matches cannot be regenerated safely."
                    )
                )
            generated_matches.unlink()
            self.env["federation.stage.progression"].search(
                [
                    ("tournament_id", "=", division.id),
                    ("source_stage_id", "=", pool_stage.id),
                    ("target_stage_id", "=", knockout_stage.id),
                    ("state", "=", "pending"),
                ]
            ).unlink()
            pool_matches = division.match_ids.filtered(
                lambda match: match.stage_id == pool_stage
            )
            knockout_matches = division.match_ids.filtered(
                lambda match: match.stage_id == knockout_stage
            )

        if not pool_matches:
            participants.write({"stage_id": pool_stage.id, "group_id": False})
            groups = self._assign_pool_then_bracket_groups(division, pool_stage, participants)
            self._ensure_pool_then_bracket_progressions(
                division,
                pool_stage,
                knockout_stage,
                groups,
            )
            return self._generate_group_round_robin_matches(division, pool_stage, groups)

        if knockout_matches:
            if not force:
                raise ValidationError(
                    _(
                        "The pool phase and knockout bracket have already been generated for this division."
                    )
                )
            return self.env["federation.match"]

        qualified_participants = self._prepare_pool_then_bracket_knockout_participants(
            division,
            knockout_stage,
        )
        required_qualifiers = division.pool_count * division.pool_qualifier_count
        if len(qualified_participants) < 2:
            raise ValidationError(
                _(
                    "Freeze the pool standings first so qualified teams can advance into the knockout stage."
                )
            )
        if len(qualified_participants) < min(required_qualifiers, len(participants)):
            raise ValidationError(
                _(
                    "Only %(qualified)s qualified teams have advanced so far. Expected %(required)s before generating the knockout bracket.",
                    qualified=len(qualified_participants),
                    required=min(required_qualifiers, len(participants)),
                )
            )
        return self._generate_knockout_matches(
            division,
            knockout_stage,
            qualified_participants,
        )

    def _generate_knockout_matches(self, division, stage, participants):
        knockout_service = self.env["federation.knockout.service"]
        teams = knockout_service._apply_seeding(participants, "seed")
        bracket_size = knockout_service._determine_bracket_size(
            len(teams), "power_of_two"
        )
        first_round_pairs = knockout_service._build_first_round(teams, bracket_size)

        Match = self.env["federation.match"]
        created_matches = Match.browse([])
        round_1_matches = []
        for bracket_position, (home_team, away_team) in enumerate(
            first_round_pairs, start=1
        ):
            match = Match.create(
                {
                    "tournament_id": division.id,
                    "stage_id": stage.id,
                    "home_team_id": home_team.id,
                    "away_team_id": away_team.id,
                    "round_number": 1,
                    "bracket_position": bracket_position,
                    "bracket_type": "winners",
                    "state": "draft",
                }
            )
            round_1_matches.append(match)
            created_matches |= match

        previous_sources = knockout_service._build_round_sources(
            teams, bracket_size, round_1_matches
        )
        round_number = 2
        while len(previous_sources) > 1:
            current_matches = []
            for index in range(len(previous_sources) // 2):
                source_a = previous_sources[index * 2]
                source_b = previous_sources[index * 2 + 1]
                vals = {
                    "tournament_id": division.id,
                    "stage_id": stage.id,
                    "round_number": round_number,
                    "bracket_position": index + 1,
                    "bracket_type": "winners",
                    "state": "draft",
                }
                if source_a["type"] == "bye":
                    vals["home_team_id"] = source_a["team"].id
                else:
                    vals["source_match_1_id"] = source_a["match"].id
                    vals["source_type_1"] = source_a.get("result", "winner")
                if source_b["type"] == "bye":
                    vals["away_team_id"] = source_b["team"].id
                else:
                    vals["source_match_2_id"] = source_b["match"].id
                    vals["source_type_2"] = source_b.get("result", "winner")
                match = Match.create(vals)
                current_matches.append(match)
                created_matches |= match

            previous_sources = [
                {"type": "match", "match": match, "result": "winner"}
                for match in current_matches
            ]
            round_number += 1

        return created_matches

    @api.model
    def generate_schedule_structure(self, division_id, force=False):
        self._check_access()
        division = self._resolve_division(division_id)
        if division.planning_format == "single_round_robin":
            stage, participants = self._prepare_generation(division, force=force)
            created_matches = self._generate_round_robin_matches(
                division,
                stage,
                participants,
                double_round=False,
            )
        elif division.planning_format == "double_round_robin":
            stage, participants = self._prepare_generation(division, force=force)
            created_matches = self._generate_round_robin_matches(
                division,
                stage,
                participants,
                double_round=True,
            )
        elif division.planning_format == "knockout":
            stage, participants = self._prepare_generation(division, force=force)
            created_matches = self._generate_knockout_matches(
                division,
                stage,
                participants,
            )
        elif division.planning_format == "pool_then_bracket":
            created_matches = self._generate_pool_then_bracket_matches(
                division,
                force=force,
            )
        else:
            raise ValidationError(
                _(
                    "The Competition Workspace does not support guided generation for the selected planning format yet."
                )
            )

        division._competition_workspace_transition_state("schedule_generated")
        return {
            "match_count": len(created_matches),
            "payload": self.get_competition_workspace_data(
                division.edition_id.id if division.edition_id else False,
                division.id,
            ),
        }

    @api.model
    def generate_round_robin(self, division_id, force=False):
        return self.generate_schedule_structure(division_id, force=force)

    @api.model
    def create_gameday(self, vals):
        self._check_access()
        division = self._resolve_division(vals["division_id"])
        stage = self._resolve_workspace_stage(division, stage_id=vals.get("stage_id"))
        shared_divisions = self._resolve_shared_divisions(
            division,
            vals.get("shared_division_ids"),
        )
        sequence = vals.get("sequence") or (
            max(
                division.round_ids.filtered(lambda round_record: round_record.stage_id == stage).mapped("sequence")
                or [0]
            )
            + 1
        )
        round_vals = {
            "name": vals.get("name") or _("Gameday %(number)s", number=sequence),
            "stage_id": stage.id,
            "sequence": sequence,
            "round_date": vals.get("round_date"),
            "planner_state": vals.get("planner_state", "draft"),
            "venue_id": vals.get("venue_id")
            if "venue_id" in self.env["federation.tournament.round"]._fields
            else False,
        }
        gameday = self.env["federation.tournament.round"].create(round_vals)
        for shared_division in shared_divisions:
            shared_stage = self._resolve_workspace_stage(
                shared_division,
                stage_type=stage.stage_type,
            )
            self.env["federation.tournament.round"].create(
                {
                    **round_vals,
                    "stage_id": shared_stage.id,
                    "planner_root_round_id": gameday.id,
                }
            )
        if division.workspace_state in ("registration_locked", "schedule_generated"):
            division._competition_workspace_transition_state("planning")
        for shared_division in shared_divisions.filtered(
            lambda record: record.workspace_state in ("registration_locked", "schedule_generated")
        ):
            shared_division._competition_workspace_transition_state("planning")
        return {
            "gameday_id": gameday.id,
            "payload": self.get_competition_workspace_data(
                division.edition_id.id if division.edition_id else False,
                division.id,
            ),
        }

    def _normalize_breaks(self, breaks):
        normalized = []
        for break_item in breaks or []:
            start_value = self._normalize_time_value(break_item.get("start"), _("Break start"))
            end_value = self._normalize_time_value(break_item.get("end"), _("Break end"))
            if end_value <= start_value:
                raise ValidationError(_("Each break must end after it starts."))
            normalized.append(
                {
                    "start": start_value,
                    "end": end_value,
                    "label": break_item.get("label") or _("Break"),
                }
            )
        return sorted(normalized, key=lambda item: item["start"])

    def _combine_gameday_time(self, gameday, value, label):
        if not gameday.round_date:
            raise ValidationError(
                _("Set a date on the gameday before generating planner slots.")
            )
        return datetime.combine(
            fields.Date.to_date(gameday.round_date),
            self._normalize_time_value(value, label),
        )

    def _clear_existing_slots(self, gameday, force, capabilities):
        existing_slots = gameday.slot_ids
        if not existing_slots:
            return
        assigned_slots = existing_slots.filtered("match_id")
        if assigned_slots and not force:
            raise ValidationError(
                _("This gameday already has assigned slots. Use force regeneration only when you intend to clear them.")
            )
        if assigned_slots and force and not capabilities["can_force_assign"]:
            raise AccessError(
                _("Only federation managers can force-regenerate a gameday that already carries assigned matches.")
            )
        for slot in assigned_slots:
            self._apply_unassignment(slot.match_id, allow_locked=True)
        existing_slots.unlink()

    def _build_slot_windows(self, gameday, start_dt, end_dt, match_duration_minutes, buffer_minutes, breaks):
        windows = []
        pointer = start_dt
        duration = timedelta(minutes=match_duration_minutes)
        buffer_delta = timedelta(minutes=buffer_minutes)
        break_windows = [
            {
                "start": datetime.combine(fields.Date.to_date(gameday.round_date), item["start"]),
                "end": datetime.combine(fields.Date.to_date(gameday.round_date), item["end"]),
                "label": item["label"],
            }
            for item in breaks
        ]

        while pointer < end_dt:
            active_break = next(
                (
                    break_item
                    for break_item in break_windows
                    if break_item["start"] <= pointer < break_item["end"]
                ),
                False,
            )
            if active_break:
                windows.append(
                    {
                        "state": "break",
                        "start": pointer,
                        "end": min(active_break["end"], end_dt),
                        "label": active_break["label"],
                    }
                )
                pointer = active_break["end"]
                continue

            if pointer + duration > end_dt:
                break

            upcoming_break = next(
                (
                    break_item
                    for break_item in break_windows
                    if pointer < break_item["start"] < pointer + duration
                ),
                False,
            )
            if upcoming_break:
                pointer = upcoming_break["start"]
                continue

            windows.append(
                {
                    "state": "available",
                    "start": pointer,
                    "end": pointer + duration,
                    "label": False,
                }
            )
            pointer += duration + buffer_delta

        return windows

    @api.model
    def generate_slots(
        self,
        gameday_id,
        court_ids,
        start_time,
        end_time,
        match_duration_minutes,
        buffer_minutes,
        breaks=None,
        force=False,
        expected_planner_revision=False,
    ):
        capabilities = self._check_access()
        gameday = self._resolve_gameday(gameday_id)
        gameday_root = self._ensure_planner_write_revision(
            gameday, expected_planner_revision
        )
        if not court_ids:
            raise ValidationError(_("Select at least one court before generating slots."))
        courts = self.env["federation.playing.area"].browse(court_ids).exists()
        if len(courts) != len(court_ids):
            raise ValidationError(_("One or more selected courts could not be found."))

        venue = False
        if "venue_id" in gameday_root._fields and gameday_root.venue_id:
            venue = gameday_root.venue_id
        else:
            venue = courts[:1].venue_id
            if "venue_id" in gameday_root._fields:
                gameday_root.venue_id = venue.id
        if any(court.venue_id != venue for court in courts):
            raise ValidationError(
                _("All selected courts must belong to the same venue as the gameday.")
            )

        start_dt = self._combine_gameday_time(gameday_root, start_time, _("Start time"))
        end_dt = self._combine_gameday_time(gameday_root, end_time, _("End time"))
        if end_dt <= start_dt:
            raise ValidationError(_("The slot generation end time must be after the start time."))
        if match_duration_minutes <= 0:
            raise ValidationError(_("Match duration must be a positive number of minutes."))
        if buffer_minutes < 0:
            raise ValidationError(_("Buffer duration cannot be negative."))

        normalized_breaks = self._normalize_breaks(breaks)
        self._clear_existing_slots(gameday_root, force, capabilities)
        windows = self._build_slot_windows(
            gameday_root,
            start_dt,
            end_dt,
            match_duration_minutes,
            buffer_minutes,
            normalized_breaks,
        )
        Slot = self.env["federation.match.slot"]
        sequence = 10
        created_slots = Slot.browse([])
        for court in courts:
            for window in windows:
                created_slots |= Slot.create(
                    {
                        "round_id": gameday_root.id,
                        "venue_id": venue.id,
                        "playing_area_id": court.id,
                        "start_datetime": window["start"],
                        "end_datetime": window["end"],
                        "state": window["state"],
                        "note": window["label"],
                        "sequence": sequence,
                    }
                )
                sequence += 10
        (gameday_root | gameday_root.planner_linked_round_ids)._competition_workspace_transition_planner_state(
            "planned"
        )
        self._get_gameday_divisions(gameday_root).filtered(
            lambda record: record.workspace_state == "schedule_generated"
        )._competition_workspace_transition_state("planning")
        self._ensure_draft_schedule_revision(gameday_root)
        self._bump_planner_revision(gameday_root)
        return {
            "slot_count": len(created_slots),
            "planner": self.get_gameday_planner_data(gameday.id),
        }

    def _mark_schedule_dirty(self, division, gameday=False):
        affected_divisions = division
        if gameday:
            planner_root = self._get_planner_root_gameday(gameday)
            self._ensure_draft_schedule_revision(planner_root)
            affected_rounds = planner_root | planner_root.planner_linked_round_ids
            if any(round_record.planner_state in ("validated", "published") for round_record in affected_rounds):
                affected_rounds._competition_workspace_transition_planner_state(
                    "planned",
                    reason=_(
                        "Planner changes reopened the gameday for review before publication."
                    ),
                    actor=self.env.user,
                )
            affected_divisions |= self._get_gameday_divisions(planner_root)
        affected_divisions.filtered(
            lambda record: record.workspace_state in ("published", "schedule_generated")
        )._competition_workspace_transition_state(
            "planning",
            reason=_(
                "Planner changes reopened the division schedule for review before publication."
            ),
            actor=self.env.user,
        )

    def _clear_redo_planner_operations(self, gameday):
        planner_root = self._get_planner_root_gameday(gameday)
        self._planner_operation_model().search(
            [
                ("planner_root_round_id", "=", planner_root.id),
                ("state", "=", "undone"),
            ]
        ).write({"state": "superseded"})
        return True

    def _record_planner_operation(
        self,
        match,
        old_slot=False,
        new_slot=False,
        forced=False,
        batch_key=False,
        override_reason=False,
    ):
        old_slot = old_slot.exists() if old_slot else False
        new_slot = new_slot.exists() if new_slot else False
        if old_slot and new_slot and old_slot == new_slot:
            return False
        if old_slot and new_slot:
            operation_type = "move"
            planner_root = self._get_planner_root_gameday(new_slot.round_id)
        elif new_slot:
            operation_type = "assign"
            planner_root = self._get_planner_root_gameday(new_slot.round_id)
        elif old_slot:
            operation_type = "unassign"
            planner_root = self._get_planner_root_gameday(old_slot.round_id)
        else:
            return False
        return self._planner_operation_model().create(
            {
                "planner_root_round_id": planner_root.id,
                "match_id": match.id,
                "old_slot_id": old_slot.id if old_slot else False,
                "new_slot_id": new_slot.id if new_slot else False,
                "operation_type": operation_type,
                "user_id": self.env.user.id,
                "forced": forced,
                "batch_key": batch_key or False,
                "override_reason": self._normalize_override_reason(override_reason)
                or False,
            }
        )

    def _validate_assignment_action(
        self,
        match,
        slot,
        capabilities,
        force=False,
        override_reason=False,
        simulated_slots=None,
    ):
        validation = self.validate_match_assignment(
            match.id,
            slot.id,
            simulated_slots=simulated_slots,
        )
        if validation["blocking"]:
            return validation
        if validation["warnings"] and not force:
            return validation
        if validation["warnings"] and force and not capabilities["can_force_assign"]:
            raise AccessError(
                _("Only federation managers can force an assignment after warnings.")
            )
        if validation["warnings"] and force and not self._normalize_override_reason(
            override_reason
        ):
            return self._planner_override_reason_required(
                validation,
                _(
                    "Provide a manager reason before forcing a warning-only assignment."
                ),
                record_id=match.id,
            )
        return validation

    def _swap_target_match(self, match, slot):
        old_slot = match.slot_id.exists()
        target_match = slot.match_id.exists()
        if not old_slot or not target_match or target_match == match:
            return False
        if self._get_planner_root_gameday(old_slot.round_id) != self._get_planner_root_gameday(
            slot.round_id
        ):
            return False
        return target_match

    def _validate_swap_action(
        self,
        match,
        slot,
        displaced_match,
        capabilities,
        force=False,
        override_reason=False,
    ):
        old_slot = match.slot_id.exists()
        simulated_slots = {
            match.id: slot,
            displaced_match.id: old_slot,
        }
        validation = self._merge_planner_validations(
            self._validate_assignment_action(
                match,
                slot,
                capabilities,
                force=force,
                override_reason=override_reason,
                simulated_slots=simulated_slots,
            ),
            self._validate_assignment_action(
                displaced_match,
                old_slot,
                capabilities,
                force=force,
                override_reason=override_reason,
                simulated_slots=simulated_slots,
            ),
        )
        if validation["warnings"] and force and not self._normalize_override_reason(
            override_reason
        ):
            return self._planner_override_reason_required(
                validation,
                _(
                    "Provide a manager reason before forcing a warning-only swap."
                ),
                record_id=match.id,
            )
        return validation

    def _latest_planner_operation_group(self, gameday, state="applied"):
        planner_root = self._get_planner_root_gameday(gameday)
        latest_operation = self._planner_operation_model().search(
            [
                ("planner_root_round_id", "=", planner_root.id),
                ("state", "=", state),
            ],
            order="id desc",
            limit=1,
        )
        if not latest_operation:
            return latest_operation
        if latest_operation.batch_key:
            return self._planner_operation_model().search(
                [
                    ("planner_root_round_id", "=", planner_root.id),
                    ("batch_key", "=", latest_operation.batch_key),
                    ("state", "=", state),
                ],
                order="id desc" if state == "applied" else "id asc",
            )
        return latest_operation

    def _undo_planner_operation(self, operation, capabilities):
        match = operation.match_id.exists()
        if not match:
            raise ValidationError(
                _("The match from the selected planner action could not be found.")
            )
        if operation.operation_type == "assign":
            self._apply_unassignment(
                match,
                bump_revision=False,
                record_operation=False,
            )
            return self._planner_validation()
        target_slot = operation.old_slot_id.exists()
        if not target_slot:
            raise ValidationError(
                _("The original slot for this planner action is no longer available.")
            )
        validation = self._validate_assignment_action(
            match,
            target_slot,
            capabilities,
            force=operation.forced,
            override_reason=operation.override_reason,
        )
        if validation["blocking"] or (validation["warnings"] and not operation.forced):
            return validation
        self._apply_assignment(
            match,
            target_slot,
            forced=operation.forced,
            bump_revision=False,
            record_operation=False,
        )
        return validation

    def _redo_planner_operation(self, operation, capabilities):
        match = operation.match_id.exists()
        if not match:
            raise ValidationError(
                _("The match from the selected planner action could not be found.")
            )
        if operation.operation_type == "unassign":
            self._apply_unassignment(
                match,
                bump_revision=False,
                record_operation=False,
            )
            return self._planner_validation()
        target_slot = operation.new_slot_id.exists()
        if not target_slot:
            raise ValidationError(
                _("The destination slot for this planner action is no longer available.")
            )
        validation = self._validate_assignment_action(
            match,
            target_slot,
            capabilities,
            force=operation.forced,
            override_reason=operation.override_reason,
        )
        if validation["blocking"] or (validation["warnings"] and not operation.forced):
            return validation
        self._apply_assignment(
            match,
            target_slot,
            forced=operation.forced,
            bump_revision=False,
            record_operation=False,
        )
        return validation

    def _apply_assignment(
        self,
        match,
        slot,
        forced=False,
        override_reason=False,
        bump_revision=True,
        record_operation=True,
        batch_key=False,
    ):
        planner_round = self._get_match_planner_round(slot.round_id, match)
        if not planner_round:
            raise ValidationError(
                _("The selected slot is not linked to the match division's shared gameday."),
            )
        old_slot = match.slot_id
        if old_slot and old_slot != slot:
            old_slot.write({"match_id": False})
        write_vals = {
            "slot_id": slot.id,
            "round_id": planner_round.id,
            "date_scheduled": slot.start_datetime,
        }
        if "venue_id" in match._fields:
            write_vals["venue_id"] = slot.venue_id.id
        if "playing_area_id" in match._fields:
            write_vals["playing_area_id"] = slot.playing_area_id.id
        match.write(write_vals)
        if match.state == "draft":
            match.action_schedule()
        slot.write({"match_id": match.id})
        self._mark_schedule_dirty(match.tournament_id, slot.round_id)
        if record_operation:
            self._record_planner_operation(
                match,
                old_slot=old_slot,
                new_slot=slot,
                forced=forced,
                batch_key=batch_key,
                override_reason=override_reason,
            )
        if bump_revision:
            self._bump_planner_revision(slot.round_id)

    def _apply_swap_assignment(
        self,
        match,
        slot,
        displaced_match,
        forced=False,
        override_reason=False,
        bump_revision=True,
        record_operation=True,
        batch_key=False,
    ):
        old_slot = match.slot_id.exists()
        target_slot = slot.exists()
        displaced_old_slot = displaced_match.slot_id.exists()
        if not old_slot or not target_slot or displaced_old_slot != target_slot:
            raise ValidationError(
                _(
                    "The target slot is no longer occupied by the expected match for a safe swap."
                )
            )

        match_target_round = self._get_match_planner_round(target_slot.round_id, match)
        displaced_target_round = self._get_match_planner_round(
            old_slot.round_id,
            displaced_match,
        )
        if not match_target_round or not displaced_target_round:
            raise ValidationError(
                _(
                    "One of the selected matches is no longer linked to this shared gameday."
                )
            )

        swap_batch_key = batch_key or uuid4().hex
        old_slot.write({"match_id": False})
        target_slot.write({"match_id": False})

        match_vals = {
            "slot_id": target_slot.id,
            "round_id": match_target_round.id,
            "date_scheduled": target_slot.start_datetime,
        }
        displaced_vals = {
            "slot_id": old_slot.id,
            "round_id": displaced_target_round.id,
            "date_scheduled": old_slot.start_datetime,
        }
        if "venue_id" in match._fields:
            match_vals["venue_id"] = target_slot.venue_id.id
        if "playing_area_id" in match._fields:
            match_vals["playing_area_id"] = target_slot.playing_area_id.id
        if "venue_id" in displaced_match._fields:
            displaced_vals["venue_id"] = old_slot.venue_id.id
        if "playing_area_id" in displaced_match._fields:
            displaced_vals["playing_area_id"] = old_slot.playing_area_id.id

        match.write(match_vals)
        displaced_match.write(displaced_vals)
        if match.state == "draft":
            match.action_schedule()
        if displaced_match.state == "draft":
            displaced_match.action_schedule()

        target_slot.write({"match_id": match.id})
        old_slot.write({"match_id": displaced_match.id})
        self._mark_schedule_dirty(
            match.tournament_id | displaced_match.tournament_id,
            target_slot.round_id,
        )
        if record_operation:
            self._record_planner_operation(
                match,
                old_slot=old_slot,
                new_slot=target_slot,
                forced=forced,
                batch_key=swap_batch_key,
                override_reason=override_reason,
            )
            self._record_planner_operation(
                displaced_match,
                old_slot=target_slot,
                new_slot=old_slot,
                forced=forced,
                batch_key=swap_batch_key,
                override_reason=override_reason,
            )
        if bump_revision:
            self._bump_planner_revision(target_slot.round_id)
        return swap_batch_key

    def _is_swap_operation_group(self, operations):
        if len(operations) != 2 or any(
            operation.operation_type != "move" for operation in operations
        ):
            return False
        first, second = operations[0], operations[1]
        return bool(
            first.old_slot_id
            and first.new_slot_id
            and second.old_slot_id
            and second.new_slot_id
            and first.old_slot_id == second.new_slot_id
            and first.new_slot_id == second.old_slot_id
        )

    def _apply_swap_operation_group(self, operations, capabilities, direction):
        primary = operations[0]
        counterpart = operations[1]
        match = primary.match_id.exists()
        displaced_match = counterpart.match_id.exists()
        if not match or not displaced_match:
            raise ValidationError(
                _("One of the matches from the selected swap action could not be found.")
            )
        target_slot = (
            primary.old_slot_id.exists() if direction == "undo" else primary.new_slot_id.exists()
        )
        validation = self._validate_swap_action(
            match,
            target_slot,
            displaced_match,
            capabilities,
            force=primary.forced or counterpart.forced,
            override_reason=primary.override_reason or counterpart.override_reason,
        )
        if validation["blocking"] or validation["warnings"]:
            return validation
        self._apply_swap_assignment(
            match,
            target_slot,
            displaced_match,
            forced=primary.forced or counterpart.forced,
            override_reason=primary.override_reason or counterpart.override_reason,
            bump_revision=False,
            record_operation=False,
            batch_key=primary.batch_key or counterpart.batch_key,
        )
        return validation

    def _apply_unassignment(
        self,
        match,
        allow_locked=False,
        bump_revision=True,
        record_operation=True,
        batch_key=False,
    ):
        capabilities = self._check_access()
        if not allow_locked:
            blocking_issue = self._validation_service().match_move_blocking_issue(
                self, match, capabilities
            )
            if blocking_issue:
                raise ValidationError(blocking_issue["message"])
        old_slot = match.slot_id
        old_round = match.round_id
        if old_slot:
            old_slot.write({"match_id": False})
        write_vals = {
            "slot_id": False,
            "round_id": False,
            "date_scheduled": False,
        }
        if "venue_id" in match._fields:
            write_vals["venue_id"] = False
        if "playing_area_id" in match._fields:
            write_vals["playing_area_id"] = False
        match.write(write_vals)
        if match.state == "scheduled":
            match.action_draft()
        dirty_gameday = old_round or old_slot.round_id if old_slot else old_round
        self._mark_schedule_dirty(
            match.tournament_id,
            dirty_gameday,
        )
        if record_operation and old_slot:
            self._record_planner_operation(
                match,
                old_slot=old_slot,
                new_slot=False,
                batch_key=batch_key,
            )
        if bump_revision and dirty_gameday:
            self._bump_planner_revision(dirty_gameday)

    @api.model
    def assign_match_to_slot(
        self,
        match_id,
        slot_id,
        force=False,
        expected_planner_revision=False,
        override_reason=False,
        idempotency_key=False,
    ):
        capabilities = self._check_access()
        match = self._resolve_match(match_id)
        slot = self._resolve_slot(slot_id)
        idempotency_scope = "assign_match_to_slot"
        replay_operations = self._idempotency_applied_operations(
            self._get_planner_root_gameday(slot.round_id),
            idempotency_scope,
            idempotency_key=idempotency_key,
        )
        if self._assert_idempotent_assign_intent(replay_operations, match, slot):
            return self._idempotency_replay_response(
                self._get_planner_root_gameday(slot.round_id),
                idempotency_scope,
                idempotency_key=idempotency_key,
            )

        planner_root, conflict = self._ensure_planner_write_revision_or_conflict(
            slot.round_id,
            expected_planner_revision,
            operation="assign_match_to_slot",
        )
        if conflict:
            return conflict
        batch_key = self._idempotency_batch_key(
            idempotency_scope,
            idempotency_key=idempotency_key,
        )
        displaced_match = self._swap_target_match(match, slot)
        validation = (
            self._validate_swap_action(
                match,
                slot,
                displaced_match,
                capabilities,
                force=force,
                override_reason=override_reason,
            )
            if displaced_match
            else self._validate_assignment_action(
                match,
                slot,
                capabilities,
                force=force,
                override_reason=override_reason,
            )
        )
        if validation["blocking"] or (validation["warnings"] and not force):
            return {"ok": False, "validation": validation}
        self._clear_redo_planner_operations(planner_root)
        if displaced_match:
            self._apply_swap_assignment(
                match,
                slot,
                displaced_match,
                forced=force,
                override_reason=override_reason,
                batch_key=batch_key,
            )
        else:
            self._apply_assignment(
                match,
                slot,
                forced=force,
                override_reason=override_reason,
                batch_key=batch_key,
            )
        response = {
            "ok": True,
            "validation": validation,
            "planner": self.get_gameday_planner_data(slot.round_id.id),
        }
        response["idempotency"] = self._idempotency_metadata(
            idempotency_scope,
            idempotency_key=idempotency_key,
            replayed=False,
        )
        return response

    @api.model
    def unassign_match(
        self,
        match_id,
        expected_planner_revision=False,
        idempotency_key=False,
    ):
        self._check_access()
        match = self._resolve_match(match_id)
        idempotency_scope = "unassign_match"
        gameday = match.slot_id.round_id if match.slot_id else False
        planner_root = self._get_planner_root_gameday(gameday) if gameday else False
        if planner_root:
            replay_operations = self._idempotency_applied_operations(
                planner_root,
                idempotency_scope,
                idempotency_key=idempotency_key,
            )
            if self._assert_idempotent_unassign_intent(replay_operations, match):
                return self._idempotency_replay_response(
                    planner_root,
                    idempotency_scope,
                    idempotency_key=idempotency_key,
                )
        else:
            replay_operations = self._idempotency_applied_operations_for_match(
                match,
                idempotency_scope,
                idempotency_key=idempotency_key,
            )
            if self._assert_idempotent_unassign_intent(replay_operations, match):
                replay_root = replay_operations[:1].planner_root_round_id
                if replay_root:
                    return self._idempotency_replay_response(
                        replay_root,
                        idempotency_scope,
                        idempotency_key=idempotency_key,
                    )

        if gameday:
            planner_root, conflict = self._ensure_planner_write_revision_or_conflict(
                gameday,
                expected_planner_revision,
                operation="unassign_match",
            )
            if conflict:
                return conflict
            self._clear_redo_planner_operations(planner_root)
        self._apply_unassignment(
            match,
            batch_key=self._idempotency_batch_key(
                idempotency_scope,
                idempotency_key=idempotency_key,
            ),
        )
        response = {
            "ok": True,
            "planner": self.get_gameday_planner_data(gameday.id) if gameday else False,
        }
        response["idempotency"] = self._idempotency_metadata(
            idempotency_scope,
            idempotency_key=idempotency_key,
            replayed=False,
        )
        return response

    @api.model
    def move_match(self, match_id, target_slot_id, force=False):
        return self.assign_match_to_slot(match_id, target_slot_id, force=force)

    @api.model
    def bulk_assign_matches(
        self,
        gameday_id,
        match_ids,
        force=False,
        expected_planner_revision=False,
        override_reason=False,
    ):
        capabilities = self._check_access()
        planner_root, conflict = self._ensure_planner_write_revision_or_conflict(
            self._resolve_gameday(gameday_id),
            expected_planner_revision,
            operation="bulk_assign_matches",
        )
        if conflict:
            return conflict
        matches = self._resolve_matches(match_ids)
        if not matches:
            return {
                "ok": False,
                "validation": self._planner_blocking_validation(
                    "no_selected_matches",
                    _("Select one or more unscheduled matches before bulk assigning them."),
                ),
            }
        assigned_match = next((match for match in matches if match.slot_id), False)
        if assigned_match:
            return {
                "ok": False,
                "validation": self._planner_blocking_validation(
                    "bulk_assign_requires_unscheduled",
                    _("Bulk assign only accepts currently unscheduled matches."),
                    record_id=assigned_match.id,
                ),
            }
        open_slots = list(self._get_open_planner_slots(planner_root))
        if len(open_slots) < len(matches):
            return {
                "ok": False,
                "validation": self._planner_blocking_validation(
                    "insufficient_open_slots",
                    _(
                        "There are not enough open slots on this gameday to place the selected matches."
                    ),
                ),
            }
        batch_key = uuid4().hex
        self._clear_redo_planner_operations(planner_root)
        try:
            with self.env.cr.savepoint():
                for match, slot in zip(matches, open_slots):
                    validation = self._validate_assignment_action(
                        match,
                        slot,
                        capabilities,
                        force=force,
                        override_reason=override_reason,
                    )
                    if validation["blocking"] or (
                        validation["warnings"] and not force
                    ):
                        raise PlannerOperationRollback(
                            {"ok": False, "validation": validation}
                        )
                    self._apply_assignment(
                        match,
                        slot,
                        forced=force,
                        override_reason=override_reason,
                        bump_revision=False,
                        batch_key=batch_key,
                    )
                self._bump_planner_revision(planner_root)
        except PlannerOperationRollback as error:
            return error.result
        return {
            "ok": True,
            "operation_count": len(matches),
            "planner": self.get_gameday_planner_data(planner_root.id),
        }

    @api.model
    def bulk_unassign_matches(
        self,
        gameday_id,
        match_ids,
        expected_planner_revision=False,
    ):
        self._check_access()
        planner_root, conflict = self._ensure_planner_write_revision_or_conflict(
            self._resolve_gameday(gameday_id),
            expected_planner_revision,
            operation="bulk_unassign_matches",
        )
        if conflict:
            return conflict
        matches = self._resolve_matches(match_ids)
        if not matches:
            return {
                "ok": False,
                "validation": self._planner_blocking_validation(
                    "no_selected_matches",
                    _("Select one or more assigned matches before bulk unassigning them."),
                ),
            }
        unassigned_match = next((match for match in matches if not match.slot_id), False)
        if unassigned_match:
            return {
                "ok": False,
                "validation": self._planner_blocking_validation(
                    "bulk_unassign_requires_assigned",
                    _("Bulk unassign only accepts currently assigned matches."),
                    record_id=unassigned_match.id,
                ),
            }
        foreign_match = next(
            (
                match
                for match in matches
                if self._get_planner_root_gameday(match.slot_id.round_id) != planner_root
            ),
            False,
        )
        if foreign_match:
            return {
                "ok": False,
                "validation": self._planner_blocking_validation(
                    "cross_gameday_selection",
                    _("Bulk unassign only accepts matches from the active gameday."),
                    record_id=foreign_match.id,
                ),
            }
        batch_key = uuid4().hex
        self._clear_redo_planner_operations(planner_root)
        with self.env.cr.savepoint():
            for match in matches:
                self._apply_unassignment(
                    match,
                    bump_revision=False,
                    batch_key=batch_key,
                )
            self._bump_planner_revision(planner_root)
        return {
            "ok": True,
            "operation_count": len(matches),
            "planner": self.get_gameday_planner_data(planner_root.id),
        }

    @api.model
    def undo_last_planner_operation(self, gameday_id, expected_planner_revision=False):
        capabilities = self._check_access()
        planner_root, conflict = self._ensure_planner_write_revision_or_conflict(
            self._resolve_gameday(gameday_id),
            expected_planner_revision,
            operation="undo_last_planner_operation",
        )
        if conflict:
            return conflict
        operations = self._latest_planner_operation_group(planner_root, state="applied")
        if not operations:
            return {
                "ok": False,
                "validation": self._planner_blocking_validation(
                    "no_undo_available",
                    _("There is no planner action left to undo."),
                ),
            }
        try:
            with self.env.cr.savepoint():
                if self._is_swap_operation_group(operations):
                    validation = self._apply_swap_operation_group(
                        operations,
                        capabilities,
                        "undo",
                    )
                    if validation["blocking"] or validation["warnings"]:
                        raise PlannerOperationRollback(
                            {"ok": False, "validation": validation}
                        )
                else:
                    for operation in operations:
                        validation = self._undo_planner_operation(operation, capabilities)
                        if validation["blocking"] or validation["warnings"]:
                            raise PlannerOperationRollback(
                                {"ok": False, "validation": validation}
                            )
                operations.write({"state": "undone"})
                self._bump_planner_revision(planner_root)
        except PlannerOperationRollback as error:
            return error.result
        return {
            "ok": True,
            "planner": self.get_gameday_planner_data(planner_root.id),
        }

    @api.model
    def redo_last_planner_operation(self, gameday_id, expected_planner_revision=False):
        capabilities = self._check_access()
        planner_root, conflict = self._ensure_planner_write_revision_or_conflict(
            self._resolve_gameday(gameday_id),
            expected_planner_revision,
            operation="redo_last_planner_operation",
        )
        if conflict:
            return conflict
        operations = self._latest_planner_operation_group(planner_root, state="undone")
        if not operations:
            return {
                "ok": False,
                "validation": self._planner_blocking_validation(
                    "no_redo_available",
                    _("There is no planner action left to redo."),
                ),
            }
        try:
            with self.env.cr.savepoint():
                if self._is_swap_operation_group(operations):
                    validation = self._apply_swap_operation_group(
                        operations,
                        capabilities,
                        "redo",
                    )
                    if validation["blocking"] or validation["warnings"]:
                        raise PlannerOperationRollback(
                            {"ok": False, "validation": validation}
                        )
                else:
                    for operation in operations:
                        validation = self._redo_planner_operation(operation, capabilities)
                        if validation["blocking"] or validation["warnings"]:
                            raise PlannerOperationRollback(
                                {"ok": False, "validation": validation}
                            )
                operations.write({"state": "applied"})
                self._bump_planner_revision(planner_root)
        except PlannerOperationRollback as error:
            return error.result
        return {
            "ok": True,
            "planner": self.get_gameday_planner_data(planner_root.id),
        }

    def _validate_division_schedule(self, division):
        return self._validation_service()._validate_division_schedule(self, division)

    @api.model
    def validate_gameday(self, gameday_id):
        return self._validation_service().validate_gameday(self, gameday_id)

    @api.model
    def validate_competition_schedule(self, competition_id=False, division_id=False):
        return self._validation_service().validate_competition_schedule(
            self,
            competition_id=competition_id,
            division_id=division_id,
        )

    @api.model
    def validate_match_assignment(self, match_id, slot_id, simulated_slots=None):
        return self._validation_service().validate_match_assignment(
            self,
            match_id,
            slot_id,
            simulated_slots=simulated_slots,
        )

    @api.model
    def publish_gameday(
        self,
        gameday_id,
        expected_planner_revision=False,
        override_reason=False,
    ):
        self._check_access(require_publish=True)
        gameday = self._resolve_gameday(gameday_id)
        planner_root, conflict = self._ensure_planner_write_revision_or_conflict(
            gameday,
            expected_planner_revision,
            operation="publish_gameday",
        )
        if conflict:
            return conflict
        validation = self.validate_gameday(planner_root.id)
        if validation["blocking"]:
            return {"ok": False, "validation": validation}
        normalized_reason = self._normalize_override_reason(override_reason)
        if (
            validation["warnings"] or planner_root.schedule_live_revision_id
        ) and not normalized_reason:
            return {
                "ok": False,
                "validation": self._planner_override_reason_required(
                    validation,
                    _(
                        "Provide a manager reason before publishing warnings or replacing the live schedule revision."
                    ),
                    record_id=planner_root.id,
                ),
            }
        linked_rounds = planner_root | planner_root.planner_linked_round_ids
        linked_rounds._competition_workspace_transition_planner_state(
            "published",
            reason=_("Published from the Competition Workspace."),
            actor=self.env.user,
        )
        linked_rounds.write({"publish_locked": True, "state": "scheduled"})
        for slot in planner_root.slot_ids.filtered("match_id"):
            if slot.match_id.state == "draft":
                slot.match_id.action_schedule()
        self._get_gameday_divisions(planner_root).filtered(
            lambda record: record.workspace_state in ("planning", "schedule_generated")
        )._competition_workspace_transition_state(
            "published",
            reason=_("Published from the Competition Workspace."),
            actor=self.env.user,
        )
        self._bump_planner_revision(planner_root)
        self._promote_schedule_revision_to_live(
            planner_root,
            override_reason=normalized_reason,
        )
        return {
            "ok": True,
            "validation": validation,
            "payload": self.get_competition_workspace_data(
                planner_root.tournament_id.edition_id.id if planner_root.tournament_id.edition_id else False,
                gameday.tournament_id.id,
            ),
        }

    @api.model
    def publish_competition_schedule(
        self,
        competition_id=False,
        division_id=False,
        override_reason=False,
    ):
        self._check_access(require_publish=True)
        validation = self.validate_competition_schedule(
            competition_id=competition_id,
            division_id=division_id,
        )
        if validation["blocking"] or validation["unscheduled_matches"]:
            return {"ok": False, "validation": validation}

        if division_id:
            divisions = self._resolve_division(division_id)
        else:
            divisions = self._resolve_competition(competition_id).tournament_ids

        planner_roots = self.env["federation.tournament.round"]
        processed_root_ids = set()
        for division in divisions:
            for gameday in self._get_division_gamedays(division):
                planner_root = self._get_planner_root_gameday(gameday)
                if planner_root.id in processed_root_ids:
                    continue
                processed_root_ids.add(planner_root.id)
                planner_roots |= planner_root

        normalized_reason = self._normalize_override_reason(override_reason)
        if (
            validation["warnings"]
            or any(root.schedule_live_revision_id for root in planner_roots)
        ) and not normalized_reason:
            return {
                "ok": False,
                "validation": self._planner_override_reason_required(
                    validation,
                    _(
                        "Provide a manager reason before publishing warnings or replacing live schedule revisions."
                    ),
                ),
            }

        for planner_root in planner_roots.sorted(
            lambda record: (record.round_date or fields.Date.today(), record.sequence, record.id)
        ):
            linked_rounds = planner_root | planner_root.planner_linked_round_ids
            linked_rounds._competition_workspace_transition_planner_state(
                "published",
                reason=_("Published from the Competition Workspace."),
                actor=self.env.user,
            )
            linked_rounds.write(
                {
                    "publish_locked": True,
                    "state": "scheduled",
                }
            )
            for slot in planner_root.slot_ids.filtered("match_id"):
                if slot.match_id.state == "draft":
                    slot.match_id.action_schedule()
            self._get_gameday_divisions(planner_root)._competition_workspace_transition_state(
                "published",
                reason=_("Published from the Competition Workspace."),
                actor=self.env.user,
            )
            self._bump_planner_revision(planner_root)
            self._promote_schedule_revision_to_live(
                planner_root,
                override_reason=normalized_reason,
            )

        target_competition_id = competition_id or divisions[:1].edition_id.id
        return {
            "ok": True,
            "validation": validation,
            "payload": self.get_competition_workspace_data(
                target_competition_id,
                divisions[:1].id,
            ),
        }

    @api.model
    def get_gameday_planner_data(self, gameday_id, filters=None):
        return self._read_model_service().get_gameday_planner_data(
            self, gameday_id, filters=filters
        )

    @api.model
    def get_match_slot_suggestions(self, match_id, gameday_id, limit=5):
        self._check_access()
        match = self._resolve_match(match_id)
        gameday = self._resolve_gameday(gameday_id)
        open_slots = self._get_open_planner_slots(gameday)
        if not open_slots:
            return []

        try:
            resolved_limit = max(int(limit or 5), 1)
        except (TypeError, ValueError):
            resolved_limit = 5

        suggestions = []
        slot_count = len(open_slots)
        for index, slot in enumerate(open_slots):
            validation = self.validate_match_assignment(match.id, slot.id)
            if validation["blocking"]:
                continue

            base_components = [
                {
                    "key": "validation_headroom",
                    "label": _("Validation headroom"),
                    "score": max(0, 100 - len(validation["warnings"]) * 25),
                },
                {
                    "key": "slot_order",
                    "label": _("Schedule fit"),
                    "score": max(
                        0,
                        100
                        - (
                            round(index * 40 / max(slot_count - 1, 1))
                            if slot_count > 1
                            else 0
                        ),
                    ),
                },
            ]
            extension_components = self._workspace_extension_score_components(
                "extend_match_slot_score_components",
                match,
                slot,
                validation=validation,
            )
            score_components = base_components + extension_components
            score = round(
                sum(component.get("score", 100) for component in score_components)
                / len(score_components)
            )
            suggestions.append(
                {
                    "slot_id": slot.id,
                    "slot_name": slot.display_name,
                    "court_name": slot.playing_area_id.display_name,
                    "start_label": fields.Datetime.to_datetime(
                        slot.start_datetime
                    ).strftime("%H:%M"),
                    "end_label": fields.Datetime.to_datetime(
                        slot.end_datetime
                    ).strftime("%H:%M"),
                    "score": score,
                    "warning_count": len(validation["warnings"]),
                    "score_components": score_components,
                }
            )

        return sorted(
            suggestions,
            key=lambda item: (-item["score"], item["start_label"], item["slot_id"]),
        )[:resolved_limit]

    @api.model
    def get_competition_workspace_data(
        self, competition_id=False, division_id=False, workspace_options=None
    ):
        return self._read_model_service().get_competition_workspace_data(
            self,
            competition_id=competition_id,
            division_id=division_id,
            workspace_options=workspace_options,
        )

    @api.model
    def heartbeat_workspace_presence(
        self,
        competition_id=False,
        division_id=False,
        gameday_id=False,
        active_section="overview",
    ):
        competition = self._resolve_competition(competition_id) if competition_id else False
        division = self._resolve_division(division_id, competition=competition) if division_id else False
        gameday = self._resolve_gameday(gameday_id) if gameday_id else False
        self._touch_workspace_presence(
            competition=competition,
            division=division,
            gameday=gameday,
            active_section=active_section,
        )
        summary = self._workspace_presence_summary(
            competition=competition,
            division=division,
            gameday=gameday,
        )
        return {
            "workspace_collaboration": summary,
            "planner_collaboration": summary if gameday else False,
        }

    @api.model
    def search_available_teams(self, division_id=False, search_options=None):
        self._check_access()
        options = search_options or {}
        domain = []
        division = self._resolve_division(division_id) if division_id else False
        if division:
            registered_team_ids = division.participant_ids.mapped("team_id").ids
            if registered_team_ids:
                domain.append(("id", "not in", registered_team_ids))

        query = (options.get("query") or "").strip()
        if query:
            domain.append(("name", "ilike", query))

        club_id = options.get("club_id")
        if club_id:
            domain.append(("club_id", "=", int(club_id)))

        limit = int(options.get("limit") or 40)
        teams = self.env["federation.team"].search(domain, limit=limit, order="name asc")
        return [
            {
                "id": team.id,
                "display_name": team.display_name,
                "club_id": team.club_id.id if team.club_id else False,
                "club_name": team.club_id.display_name if team.club_id else False,
            }
            for team in teams
        ]
