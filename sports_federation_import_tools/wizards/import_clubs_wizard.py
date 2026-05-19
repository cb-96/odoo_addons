from odoo import models


class FederationImportClubsWizard(models.TransientModel):
    _name = "federation.import.clubs.wizard"
    _description = "Import Clubs Wizard"
    _inherit = "federation.import.wizard.mixin"

    def _get_import_target_model(self):
        """Return import target model."""
        return "federation.club"

    def _get_mapping_guide(self):
        """Return mapping guide."""
        return (
            "Required columns: name.\n"
            "Recommended columns for safe onboarding: code, email, phone, city.\n"
            "Duplicate detection prefers code when provided and falls back to exact club name."
        )

    def action_parse_and_import(self):
        """Execute the parse and import action."""
        self.ensure_one()
        baseline_count = self._prepare_import_execution()
        reader = self._get_csv_reader()
        self._require_columns(reader.fieldnames, ["name"])

        line_count = 0
        success_count = 0
        error_count = 0
        errors = []
        error_categories = {}

        Club = self.env["federation.club"]

        for row_num, row in enumerate(reader, start=2):
            line_count += 1
            name = self._get_row_value(row, "name")
            code = self._get_row_value(row, "code")

            if not name:
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "missing_required_field",
                    "Name is required.",
                )
                error_count += 1
                continue

            existing = False
            if code:
                existing = Club.search([("code", "=", code)], limit=1)
            if not existing:
                existing = Club.search([("name", "=", name)], limit=1)
            if existing:
                duplicate_key = (
                    f"code '{code}'"
                    if code and existing.code == code
                    else f"name '{name}'"
                )
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "duplicate_entry",
                    f"Club already exists (matched by {duplicate_key}).",
                )
                error_count += 1
                continue

            if self._execute_row_create(
                row_num,
                lambda: Club.create(
                    {
                        "name": name,
                        "code": code or False,
                        "email": self._get_row_value(row, "email") or False,
                        "phone": self._get_row_value(row, "phone") or False,
                        "city": self._get_row_value(row, "city") or False,
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
