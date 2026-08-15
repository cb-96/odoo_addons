from odoo import _, fields
from odoo.exceptions import ValidationError


class CompetitionWorkspaceAutoScheduleConfigMixin:
    """Auto-schedule configuration and fairness objective helpers."""

    def _auto_schedule_normalize_bool(self, value, default=False):
        if value in (False, None):
            return bool(default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("1", "true", "yes", "on"):
                return True
            if lowered in ("0", "false", "no", "off", ""):
                return False
        return bool(value)

    def _auto_schedule_normalize_mode(self, mode=False):
        if mode in (False, None, ""):
            return self._auto_schedule_default_solver_mode
        normalized = str(mode).strip().lower()
        if normalized not in ("heuristic", "hybrid", "advanced"):
            raise ValidationError(
                _("Auto-schedule mode must be one of: heuristic, hybrid, advanced.")
            )
        return normalized

    def _auto_schedule_normalize_weights(self, weights=False):
        resolved = dict(self._auto_schedule_default_weights)
        if weights in (False, None, ""):
            return resolved
        if not isinstance(weights, dict):
            raise ValidationError(
                _("Auto-schedule fairness weights must be provided as a dictionary.")
            )
        allowed_keys = set(resolved)
        unknown_keys = sorted(set(weights) - allowed_keys)
        if unknown_keys:
            raise ValidationError(
                _(
                    "Unsupported auto-schedule fairness weight keys: %(keys)s",
                    keys=", ".join(unknown_keys),
                )
            )

        for key in resolved:
            if key not in weights:
                continue
            try:
                resolved[key] = max(float(weights.get(key)), 0.0)
            except (TypeError, ValueError):
                raise ValidationError(
                    _(
                        "Auto-schedule fairness weight '%(key)s' must be numeric.",
                        key=key,
                    )
                )
        return resolved

    def _auto_schedule_resolve_config(self, config=False):
        config = config or {}
        if not isinstance(config, dict):
            raise ValidationError(
                _("Auto-schedule config must be provided as a dictionary.")
            )

        mode = self._auto_schedule_normalize_mode(config.get("solver_mode"))
        enable_repair = self._auto_schedule_normalize_bool(
            config.get("enable_repair"),
            default=True,
        )
        enable_augmentation = self._auto_schedule_normalize_bool(
            config.get("enable_augmentation"),
            default=True,
        )
        if mode == "heuristic":
            enable_repair = False
            enable_augmentation = False

        repair_step_limit = config.get("repair_step_limit")
        if repair_step_limit in (False, None, ""):
            repair_step_limit = self._auto_schedule_default_repair_step_limit
        try:
            repair_step_limit = max(1, int(repair_step_limit))
        except (TypeError, ValueError):
            raise ValidationError(
                _("Auto-schedule repair_step_limit must be a positive integer.")
            )

        augmentation_step_limit = config.get("augmentation_step_limit")
        if augmentation_step_limit in (False, None, ""):
            augmentation_step_limit = (
                self._auto_schedule_default_augmentation_step_limit
            )
        try:
            augmentation_step_limit = max(1, int(augmentation_step_limit))
        except (TypeError, ValueError):
            raise ValidationError(
                _("Auto-schedule augmentation_step_limit must be a positive integer.")
            )

        weights = self._auto_schedule_normalize_weights(config.get("weights"))

        return {
            "solver_mode": mode,
            "enable_repair": enable_repair,
            "enable_augmentation": enable_augmentation,
            "repair_step_limit": repair_step_limit,
            "augmentation_step_limit": augmentation_step_limit,
            "weights": weights,
        }

    def _auto_schedule_objective_from_slot_map(
        self, slot_by_match, match_lookup, weights
    ):
        def _variance(values):
            if len(values) <= 1:
                return 0.0
            average = sum(values) / len(values)
            return sum((value - average) ** 2 for value in values)

        team_windows = {}
        for match_id in sorted(slot_by_match):
            slot = slot_by_match.get(match_id)
            match = match_lookup.get(match_id)
            if not slot or not match:
                continue
            if not slot.start_datetime:
                continue
            slot_start = fields.Datetime.to_datetime(slot.start_datetime)
            slot_end = (
                fields.Datetime.to_datetime(slot.end_datetime)
                if slot.end_datetime
                else slot_start
            )
            start_minutes = slot_start.hour * 60 + slot_start.minute
            for team, role in (
                (match.home_team_id, "home"),
                (match.away_team_id, "away"),
            ):
                if not team:
                    continue
                payload = team_windows.setdefault(
                    team.id,
                    {
                        "home": 0,
                        "away": 0,
                        "starts": [],
                        "windows": [],
                    },
                )
                payload[role] += 1
                payload["starts"].append(start_minutes)
                payload["windows"].append((slot_start, slot_end))

        avg_rest_values = []
        avg_start_values = []
        home_away_imbalances = []

        for payload in team_windows.values():
            home_away_imbalances.append(abs(payload["home"] - payload["away"]))
            if payload["starts"]:
                avg_start_values.append(sum(payload["starts"]) / len(payload["starts"]))
            windows = sorted(payload["windows"], key=lambda item: item[0])
            rest_gaps = [
                max(0.0, (current[0] - previous[1]).total_seconds() / 60.0)
                for previous, current in zip(windows, windows[1:])
            ]
            if rest_gaps:
                avg_rest_values.append(sum(rest_gaps) / len(rest_gaps))

        rest_penalty = _variance(avg_rest_values)
        timeslot_penalty = _variance(avg_start_values)
        home_away_penalty = sum(imbalance**2 for imbalance in home_away_imbalances)

        weighted_component_penalties = {
            "rest_fairness": weights["rest_fairness"] * rest_penalty,
            "home_away_fairness": weights["home_away_fairness"] * home_away_penalty,
            "timeslot_fairness": weights["timeslot_fairness"] * timeslot_penalty,
        }

        return {
            "tracked_team_count": len(team_windows),
            "component_penalties": {
                "rest_fairness": round(rest_penalty, 4),
                "home_away_fairness": round(home_away_penalty, 4),
                "timeslot_fairness": round(timeslot_penalty, 4),
            },
            "weighted_component_penalties": {
                key: round(value, 4)
                for key, value in weighted_component_penalties.items()
            },
            "total_penalty": round(sum(weighted_component_penalties.values()), 4),
        }

    def _auto_schedule_objective_delta(self, before_objective, after_objective):
        before_components = before_objective.get("component_penalties") or {}
        after_components = after_objective.get("component_penalties") or {}
        keys = sorted(set(before_components) | set(after_components))
        return {
            "total_penalty_delta": round(
                float(after_objective.get("total_penalty") or 0.0)
                - float(before_objective.get("total_penalty") or 0.0),
                4,
            ),
            "component_penalty_deltas": {
                key: round(
                    float(after_components.get(key) or 0.0)
                    - float(before_components.get(key) or 0.0),
                    4,
                )
                for key in keys
            },
        }
