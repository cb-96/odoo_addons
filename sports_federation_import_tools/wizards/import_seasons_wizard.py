from datetime import datetime

from odoo import models


class FederationImportSeasonsWizard(models.TransientModel):
    _name = "federation.import.seasons.wizard"
    _description = "Import Seasons Wizard"
    _inherit = "federation.import.wizard.mixin"

    PLANNING_TARGET_COLUMNS = (
        "target_club_count",
        "target_team_count",
        "target_tournament_count",
        "target_participant_count",
    )

    def _get_import_target_model(self):
        """Return import target model."""
        return "federation.season"

    def _get_mapping_guide(self):
        """Return mapping guide."""
        return (
            "Required columns: name, code, date_start, date_end.\n"
            "Optional columns: state, notes, target_club_count, target_team_count, "
            "target_tournament_count, target_participant_count.\n"
            "Duplicate detection prefers season code and falls back to exact season name. Dates must use YYYY-MM-DD and planning targets must be whole numbers >= 0."
        )

    def action_parse_and_import(self):
        """Execute the parse and import action."""
        self.ensure_one()
        baseline_count = self._prepare_import_execution()
        reader = self._get_csv_reader()
        self._require_columns(
            reader.fieldnames, ["name", "code", "date_start", "date_end"]
        )

        Season = self.env["federation.season"]
        line_count = 0
        success_count = 0
        error_count = 0
        errors = []
        error_categories = {}

        for row_num, row in enumerate(reader, start=2):
            line_count += 1
            name = self._get_row_value(row, "name")
            code = self._get_row_value(row, "code")
            date_start_value = self._get_row_value(row, "date_start")
            date_end_value = self._get_row_value(row, "date_end")
            state = self._get_row_value(row, "state") or "draft"

            if not name or not code or not date_start_value or not date_end_value:
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "missing_required_field",
                    "Season name, code, date_start, and date_end are required.",
                )
                error_count += 1
                continue

            try:
                date_start = datetime.strptime(date_start_value, "%Y-%m-%d").date()
                date_end = datetime.strptime(date_end_value, "%Y-%m-%d").date()
            except ValueError:
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "format_error",
                    "Season dates must use YYYY-MM-DD.",
                )
                error_count += 1
                continue

            planning_target_values = {}
            planning_error = False
            for column_name in self.PLANNING_TARGET_COLUMNS:
                raw_value = self._get_row_value(row, column_name)
                if not raw_value:
                    continue
                try:
                    parsed_value = int(raw_value)
                except ValueError:
                    self._record_error(
                        errors,
                        error_categories,
                        row_num,
                        "format_error",
                        f"{column_name} must be a whole number.",
                    )
                    error_count += 1
                    planning_error = True
                    break
                if parsed_value < 0:
                    self._record_error(
                        errors,
                        error_categories,
                        row_num,
                        "format_error",
                        f"{column_name} must be zero or greater.",
                    )
                    error_count += 1
                    planning_error = True
                    break
                planning_target_values[column_name] = parsed_value

            if planning_error:
                continue

            if state not in {"draft", "open", "closed", "cancelled"}:
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "format_error",
                    f"Invalid season state '{state}'.",
                )
                error_count += 1
                continue

            existing = Season.search([("code", "=", code)], limit=1)
            if not existing:
                existing = Season.search([("name", "=", name)], limit=1)
            if existing:
                duplicate_key = (
                    f"code '{code}'" if existing.code == code else f"name '{name}'"
                )
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "duplicate_entry",
                    f"Season already exists (matched by {duplicate_key}).",
                )
                error_count += 1
                continue

            if self._execute_row_create(
                row_num,
                lambda: Season.create(
                    {
                        "name": name,
                        "code": code,
                        "date_start": date_start,
                        "date_end": date_end,
                        "state": state,
                        "notes": self._get_row_value(row, "notes") or False,
                        **planning_target_values,
                    }
                ),
                errors,
                error_categories,
            ):
                success_count += 1
            else:
                error_count += 1

        return self._finalize_import_result(
            line_count,
            success_count,
            error_count,
            errors,
            error_categories=error_categories,
            baseline_count=baseline_count,
        )
