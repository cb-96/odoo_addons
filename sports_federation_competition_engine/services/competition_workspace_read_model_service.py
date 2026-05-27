from odoo import api, fields, models


class CompetitionWorkspaceReadModelService(models.AbstractModel):
    _name = "federation.competition.workspace.read.model.service"
    _description = "Competition Workspace Read Model Service"

    _planner_default_unscheduled_limit = 40
    _planner_max_unscheduled_limit = 200

    def _safe_int(self, raw_value, default=None):
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return default

    def _planner_unscheduled_limit(self, filters):
        raw_limit = (filters or {}).get(
            "unscheduled_limit", self._planner_default_unscheduled_limit
        )
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            limit = self._planner_default_unscheduled_limit
        if limit < 1:
            limit = self._planner_default_unscheduled_limit
        return min(limit, self._planner_max_unscheduled_limit)

    def _include_planner_reference_data(self, filters):
        if not filters or "include_reference_data" not in filters:
            return True
        value = filters.get("include_reference_data")
        if isinstance(value, str):
            return value.strip().lower() not in ("", "0", "false", "no")
        return bool(value)

    def _resolve_planner_target(self, workspace_service, selected_division, gameday_id=False):
        gamedays = workspace_service._get_division_gamedays(selected_division)
        if not gamedays:
            return False
        if gameday_id:
            parsed_gameday_id = self._safe_int(gameday_id)
            if parsed_gameday_id:
                target_gameday = workspace_service._resolve_gameday(parsed_gameday_id)
                if target_gameday.id in gamedays.ids:
                    return target_gameday
                target_root = workspace_service._get_planner_root_gameday(target_gameday)
                linked_target = gamedays.filtered(
                    lambda record: record._competition_workspace_root_round() == target_root
                )[:1]
                if linked_target:
                    return linked_target
        return gamedays[:1]

    def _planner_consistency_payload(self, planner_root, filters):
        filters = filters or {}
        raw_expected = filters.get("expected_planner_revision")
        expected_revision = self._safe_int(raw_expected)
        has_expected = raw_expected is not None and str(raw_expected).strip() != ""
        invalid_expected = has_expected and expected_revision is None
        is_stale = bool(
            expected_revision is not None
            and expected_revision != planner_root.planner_revision
        )
        return {
            "current_planner_revision": planner_root.planner_revision,
            "expected_planner_revision": expected_revision if has_expected else False,
            "invalid_expected_planner_revision": invalid_expected,
            "is_stale": is_stale,
        }

    @api.model
    def get_gameday_planner_data(self, workspace_service, gameday_id, filters=None):
        workspace_service._check_access()
        filters = filters or {}
        include_reference_data = self._include_planner_reference_data(filters)
        unscheduled_limit = self._planner_unscheduled_limit(filters)
        gameday = workspace_service._resolve_gameday(gameday_id)
        planner_root = workspace_service._get_planner_root_gameday(gameday)
        division = gameday.tournament_id
        unscheduled_matches = workspace_service._get_gameday_unscheduled_matches(planner_root)

        if filters.get("division_id"):
            division_id = self._safe_int(filters["division_id"])
            if division_id:
                unscheduled_matches = unscheduled_matches.filtered(
                    lambda match: match.tournament_id.id == division_id
                )

        if filters.get("round_number"):
            round_number = self._safe_int(filters["round_number"])
            if round_number:
                unscheduled_matches = unscheduled_matches.filtered(
                    lambda match: match.round_number == round_number
                )
        if filters.get("team_id"):
            team_id = self._safe_int(filters["team_id"])
            if team_id:
                unscheduled_matches = unscheduled_matches.filtered(
                    lambda match: match.home_team_id.id == team_id
                    or match.away_team_id.id == team_id
                )

        if filters.get("conflicts_only"):
            conflicting_match_ids = {
                issue["record_id"]
                for issue in workspace_service.validate_gameday(gameday.id)["blocking"]
                if issue.get("record_id")
            }
            unscheduled_matches = unscheduled_matches.filtered(
                lambda match: match.id in conflicting_match_ids
            )

        unscheduled_total_count = len(unscheduled_matches)
        unscheduled_matches = unscheduled_matches[:unscheduled_limit]

        slots = []
        for slot in planner_root.slot_ids.sorted(
            lambda record: (record.start_datetime, record.playing_area_id.name or "", record.id)
        ):
            slots.append(
                {
                    "id": slot.id,
                    "name": slot.display_name,
                    "state": slot.state,
                    "start_datetime": workspace_service._serialize_datetime(
                        slot.start_datetime
                    ),
                    "end_datetime": workspace_service._serialize_datetime(
                        slot.end_datetime
                    ),
                    "start_label": fields.Datetime.to_datetime(
                        slot.start_datetime
                    ).strftime("%H:%M"),
                    "end_label": fields.Datetime.to_datetime(slot.end_datetime).strftime(
                        "%H:%M"
                    ),
                    "court_id": slot.playing_area_id.id,
                    "court_name": slot.playing_area_id.display_name,
                    "match": workspace_service._serialize_match_card(slot.match_id)
                    if slot.match_id
                    else False,
                    "note": slot.note,
                }
            )

        assigned_slots = planner_root.slot_ids.filtered("match_id")
        participating_divisions = workspace_service._get_gameday_divisions(
            planner_root
        ).sorted(lambda record: (record.name or "", record.id))
        planner_data = {
            "gameday": workspace_service._serialize_gameday(gameday),
            "division": workspace_service._serialize_division(division),
            "consistency": self._planner_consistency_payload(planner_root, filters),
            "slots": slots,
            "unscheduled_matches": [
                workspace_service._serialize_match_card(match)
                for match in unscheduled_matches
            ],
            "fairness_summary": workspace_service._fairness_summary(
                matches=assigned_slots.mapped("match_id")
            ),
            "unscheduled_total_count": unscheduled_total_count,
            "unscheduled_loaded_count": len(unscheduled_matches),
            "unscheduled_has_more": unscheduled_total_count > len(unscheduled_matches),
            "assigned_match_count": len(assigned_slots),
            "validation": workspace_service.validate_gameday(gameday.id),
            "operation_history": workspace_service._serialize_planner_operation_history(
                planner_root
            ),
            "can_undo": workspace_service._can_undo_planner_operations(planner_root),
            "can_redo": workspace_service._can_redo_planner_operations(planner_root),
        }
        if include_reference_data:
            planner_data.update(
                {
                    "participating_divisions": [
                        workspace_service._serialize_division_option(record)
                        for record in participating_divisions
                    ],
                    "team_options": workspace_service._get_gameday_team_options(
                        planner_root
                    ),
                    "courts": [
                        {"id": court.id, "name": court.display_name}
                        for court in planner_root.slot_ids.mapped("playing_area_id")
                    ],
                }
            )
        return planner_data

    @api.model
    def get_competition_workspace_data(
        self,
        workspace_service,
        competition_id=False,
        division_id=False,
        workspace_options=None,
    ):
        capabilities = workspace_service._check_access()
        options = workspace_options or {}
        competition = (
            workspace_service._resolve_competition(competition_id)
            if competition_id
            else False
        )
        if competition:
            divisions = competition.tournament_ids.sorted(
                lambda record: (record.date_start or fields.Date.today(), record.name or "", record.id)
            )
        elif division_id:
            divisions = workspace_service._resolve_division(division_id)
        else:
            divisions = workspace_service.env["federation.tournament"]

        selected_division = False
        if division_id:
            selected_division = workspace_service._resolve_division(
                division_id,
                competition=competition or False,
            )
        elif divisions:
            selected_division = divisions[:1]

        include_planner = options.get("include_planner", True) or bool(
            options.get("gameday_id")
        )
        planner = False
        if include_planner and selected_division:
            planner_filters = dict(options.get("planner_filters") or {})
            planner_filters.setdefault(
                "include_reference_data",
                options.get("include_planner_reference_data", True),
            )
            if "expected_planner_revision" in options:
                planner_filters.setdefault(
                    "expected_planner_revision",
                    options.get("expected_planner_revision"),
                )
            planner_target = self._resolve_planner_target(
                workspace_service,
                selected_division,
                gameday_id=options.get("gameday_id"),
            )
            if planner_target:
                planner = self.get_gameday_planner_data(
                    workspace_service,
                    planner_target.id,
                    planner_filters,
                )

        return {
            "capabilities": capabilities,
            "competition": {
                "id": competition.id if competition else False,
                "name": competition.name if competition else False,
                "season_id": competition.season_id.id if competition else False,
                "season_name": competition.season_id.display_name
                if competition and competition.season_id
                else False,
                "template_id": competition.competition_id.id if competition else False,
                "template_name": competition.competition_id.display_name
                if competition and competition.competition_id
                else False,
                "state": competition.state if competition else False,
                "state_label": workspace_service._get_state_label(
                    competition, "state", competition.state
                )
                if competition
                else False,
            },
            "overview": workspace_service._get_workspace_overview(
                competition, divisions
            ),
            "divisions": [
                workspace_service._serialize_division(division) for division in divisions
            ],
            "selected_division_id": selected_division.id if selected_division else False,
            "selected_division": {
                **workspace_service._serialize_division(selected_division),
                "generation_preview": workspace_service._serialize_generation_preview(
                    selected_division
                ),
                "team_entries": [
                    workspace_service._serialize_team_entry(entry)
                    for entry in selected_division.participant_ids.sorted(
                        lambda record: (record.seed or 9999, record.team_id.name or "")
                    )
                ],
                "rounds": workspace_service._serialize_round_preview(selected_division),
                "gamedays": [
                    workspace_service._serialize_gameday(gameday)
                    for gameday in workspace_service._get_division_gamedays(
                        selected_division
                    )
                ],
                "validation": workspace_service._validate_division_schedule(
                    selected_division
                ),
            }
            if selected_division
            else False,
            "planner": planner,
            "options": {
                "competition_templates": [
                    {"id": record.id, "name": record.display_name}
                    for record in workspace_service.env["federation.competition"].search([])
                ],
                "seasons": [
                    {"id": record.id, "name": record.display_name}
                    for record in workspace_service.env["federation.season"].search([])
                ],
                "venues": [
                    {"id": record.id, "name": record.display_name}
                    for record in workspace_service.env["federation.venue"].search([])
                ],
            },
        }
