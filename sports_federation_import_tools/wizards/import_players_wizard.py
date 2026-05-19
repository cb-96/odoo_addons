from datetime import datetime

from odoo import models
from odoo.exceptions import ValidationError


class FederationImportPlayersWizard(models.TransientModel):
    _name = "federation.import.players.wizard"
    _description = "Import Players Wizard"
    _inherit = "federation.import.wizard.mixin"

    def _get_import_target_model(self):
        """Return import target model."""
        return "federation.player"

    def _get_mapping_guide(self):
        """Return mapping guide."""
        return (
            "Required columns: first_name and last_name. Legacy full-name imports may use name.\n"
            "Recommended columns: birth_date (YYYY-MM-DD), club_code (preferred) or club_name, gender, email, phone, state.\n"
            "Duplicate detection uses first_name + last_name + birth_date, matching the player uniqueness rule."
        )

    def action_parse_and_import(self):
        """Execute the parse and import action."""
        self.ensure_one()
        baseline_count = self._prepare_import_execution()
        reader = self._get_csv_reader()
        if not any(column in reader.fieldnames for column in ("first_name", "name")):
            raise ValidationError("Missing required columns: first_name or name")
        if not any(column in reader.fieldnames for column in ("last_name", "name")):
            raise ValidationError("Missing required columns: last_name or name")

        line_count = 0
        success_count = 0
        error_count = 0
        errors = []
        error_categories = {}

        Player = self.env["federation.player"]
        Club = self.env["federation.club"]

        for row_num, row in enumerate(reader, start=2):
            line_count += 1
            first_name = self._get_row_value(row, "first_name")
            last_name = self._get_row_value(row, "last_name")
            full_name = self._get_row_value(row, "name")

            if full_name and not (first_name and last_name):
                parts = full_name.split(None, 1)
                if len(parts) == 2:
                    first_name = first_name or parts[0]
                    last_name = last_name or parts[1]

            if not first_name or not last_name:
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "missing_required_field",
                    "Player first_name and last_name are required (or provide a full name with two parts).",
                )
                error_count += 1
                continue

            birth_date = False
            birth_date_str = self._get_row_value(row, "birth_date")
            if birth_date_str:
                try:
                    birth_date = datetime.strptime(birth_date_str, "%Y-%m-%d").date()
                except ValueError:
                    self._record_error(
                        errors,
                        error_categories,
                        row_num,
                        "format_error",
                        "Invalid birth_date format (use YYYY-MM-DD).",
                    )
                    error_count += 1
                    continue

            club = False
            club_code = self._get_row_value(row, "club_code")
            club_name = self._get_row_value(row, "club_name")
            if club_code:
                club = Club.search([("code", "=", club_code)], limit=1)
            if not club and club_name:
                club = Club.search([("name", "=", club_name)], limit=1)
            if (club_code or club_name) and not club:
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "missing_reference",
                    f"Club '{club_code or club_name}' not found.",
                )
                error_count += 1
                continue

            existing = Player.search(
                [
                    ("first_name", "=", first_name),
                    ("last_name", "=", last_name),
                    ("birth_date", "=", birth_date or False),
                ],
                limit=1,
            )
            if existing:
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "duplicate_entry",
                    f"Player '{first_name} {last_name}' already exists for the provided birth date.",
                )
                error_count += 1
                continue

            if self._execute_row_create(
                row_num,
                lambda: Player.create(
                    {
                        "first_name": first_name,
                        "last_name": last_name,
                        "birth_date": birth_date,
                        "club_id": club.id if club else False,
                        "gender": self._get_row_value(row, "gender") or False,
                        "email": self._get_row_value(row, "email") or False,
                        "phone": self._get_row_value(row, "phone") or False,
                        "state": self._get_row_value(row, "state") or "active",
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
