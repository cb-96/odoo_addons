import logging
from uuid import uuid4

from odoo import _

_logger = logging.getLogger(__name__)


class CompetitionWorkspaceExtensionMixin:
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
        if (
            schema_version == 1
            and isinstance(result, dict)
            and "schema_version" in result
        ):
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
        if (
            schema_version == 1
            and isinstance(result, dict)
            and "schema_version" in result
        ):
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
        if (
            schema_version == 1
            and isinstance(result, dict)
            and "schema_version" in result
        ):
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

        for key in (
            "record_id",
            "match_id",
            "slot_id",
            "focus_record_id",
            "referee_id",
        ):
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
                for team_id in (
                    self._safe_workspace_issue_int(value) for value in team_ids
                )
                if team_id
            }
            if parsed_team_ids:
                normalized["team_ids"] = sorted(parsed_team_ids)
            else:
                normalized.pop("team_ids", None)
        elif "team_ids" in normalized:
            normalized.pop("team_ids", None)

        return normalized

    def _normalize_workspace_extension_issue_bucket(
        self, raw_issues, method_name, severity
    ):
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
                normalized_component = (
                    self._normalize_workspace_extension_score_component(
                        component,
                        method_name=method_name,
                    )
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

        label = (
            str(component.get("label") or "").strip() or key.replace("_", " ").title()
        )
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
