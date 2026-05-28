from odoo import models
from odoo.exceptions import ValidationError


class FederationImportTeamsWizard(models.TransientModel):
    _name = "federation.import.teams.wizard"
    _description = "Import Teams Wizard"
    _inherit = "federation.import.wizard.mixin"

    def _get_import_target_model(self):
        """Return import target model."""
        return "federation.team"

    def _get_mapping_guide(self):
        """Return mapping guide."""
        return (
            "Required columns: team_name (or name) and club_code (preferred) or club_name.\n"
            "Recommended columns: code, category, gender, email, phone.\n"
            "Duplicate detection prefers team code when provided and falls back to club + team name."
        )

    def action_parse_and_import(self):
        """Execute the parse and import action."""
        self.ensure_one()
        baseline_count = self._prepare_import_execution()
        reader = self._get_csv_reader()
        if not any(
            column in reader.fieldnames for column in ("club_code", "club_name")
        ):
            raise ValidationError("Missing required columns: club_code or club_name")
        if not any(column in reader.fieldnames for column in ("team_name", "name")):
            raise ValidationError("Missing required columns: team_name or name")

        line_count = 0
        success_count = 0
        error_count = 0
        errors = []
        error_categories = {}

        Team = self.env["federation.team"]
        Club = self.env["federation.club"]

        for row_num, row in enumerate(reader, start=2):
            line_count += 1
            club_code = self._get_row_value(row, "club_code")
            club_name = self._get_row_value(row, "club_name")
            team_name = self._get_row_value(row, "team_name", "name")
            team_code = self._get_row_value(row, "code", "team_code")

            if not (club_code or club_name):
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "missing_required_field",
                    "Club code or club name is required.",
                )
                error_count += 1
                continue

            if not team_name:
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "missing_required_field",
                    "Team name is required.",
                )
                error_count += 1
                continue

            club = False
            if club_code:
                club = Club.search([("code", "=", club_code)], limit=1)
            if not club and club_name:
                club = Club.search([("name", "=", club_name)], limit=1)
            if not club:
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "missing_reference",
                    f"Club '{club_code or club_name}' not found.",
                )
                error_count += 1
                continue

            existing = False
            if team_code:
                existing = Team.search([("code", "=", team_code)], limit=1)
            if not existing:
                existing = Team.search(
                    [
                        ("club_id", "=", club.id),
                        ("name", "=", team_name),
                    ],
                    limit=1,
                )
            if existing:
                duplicate_key = (
                    f"code '{team_code}'"
                    if team_code and existing.code == team_code
                    else f"club '{club.display_name}' + team '{team_name}'"
                )
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "duplicate_entry",
                    f"Team already exists (matched by {duplicate_key}).",
                )
                error_count += 1
                continue

            if self._execute_row_create(
                row_num,
                lambda: Team.create(
                    {
                        "name": team_name,
                        "code": team_code or False,
                        "club_id": club.id,
                        "category": self._get_row_value(row, "category") or "senior",
                        "gender": self._get_row_value(row, "gender") or "male",
                        "email": self._get_row_value(row, "email") or False,
                        "phone": self._get_row_value(row, "phone") or False,
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
