import base64
import csv
import hashlib
import io

from odoo import models
from odoo.exceptions import ValidationError

from odoo.addons.sports_federation_base.models.failure_feedback import (
    is_safe_operator_detail,
)


class FederationImportWizardCsvMixin(models.AbstractModel):
    _name = "federation.import.wizard.csv.mixin"
    _description = "Federation Import Wizard CSV Helpers"

    def _compute_mapping_guide(self):
        """Compute the combined built-in and wizard-specific mapping guide."""
        for wizard in self:
            parts = []
            if wizard.template_id:
                parts.append(wizard.template_id.build_mapping_guide())
            custom_guide = wizard._get_mapping_guide()
            if custom_guide:
                parts.append(custom_guide)
            wizard.mapping_guide = "\n\n".join(part for part in parts if part)

    def _default_template_id(self):
        """Return the default template bound to the current wizard model."""
        return self.env["federation.import.template"].search(
            [("wizard_model", "=", self._name)],
            limit=1,
        )

    def _get_mapping_guide(self):
        """Return any wizard-specific mapping guide supplement."""
        return ""

    def _get_import_target_model(self):
        """Return the target model for import bookkeeping."""
        return ""

    def _current_upload_checksum(self):
        """Return the checksum of the current uploaded CSV payload."""
        self.ensure_one()
        if not self.upload_file:
            raise ValidationError("Please upload a CSV file.")
        return hashlib.sha256(base64.b64decode(self.upload_file)).hexdigest()

    def _get_target_record_count(self):
        """Return the number of existing target records before or after execution."""
        self.ensure_one()
        target_model = self._get_import_target_model()
        if not target_model:
            return 0
        return self.env[target_model].search_count([])

    def _get_csv_reader(self):
        """Decode the upload and return a trimmed DictReader."""
        self.ensure_one()
        if not self.upload_file:
            raise ValidationError("Please upload a CSV file.")

        content = base64.b64decode(self.upload_file)
        content_str = content.decode("utf-8-sig")
        sample = content_str[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;")
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(io.StringIO(content_str), dialect=dialect)
        if not reader.fieldnames:
            raise ValidationError("CSV file is empty or invalid.")
        reader.fieldnames = [
            field.strip() if field else field for field in reader.fieldnames
        ]
        return reader

    def _require_columns(self, fieldnames, required_columns):
        """Raise when one or more required columns are missing."""
        missing = [column for column in required_columns if column not in fieldnames]
        if missing:
            raise ValidationError(f"Missing required columns: {', '.join(missing)}")

    def _get_row_value(self, row, *candidates):
        """Return the first non-empty candidate value from a CSV row."""
        for candidate in candidates:
            value = row.get(candidate)
            if value not in (None, False):
                stripped = value.strip()
                if stripped:
                    return stripped
        return ""

    def _record_error(self, errors, error_categories, row_num, category, message):
        """Add a row error and increment its shared category counter."""
        errors.append(f"Row {row_num} [{category}]: {message}")
        error_categories[category] = error_categories.get(category, 0) + 1

    def _categorize_exception(self, error):
        """Map common validation and execution failures into shared categories."""
        message = str(error)
        lowered = message.lower()
        if "not found" in lowered:
            return "missing_reference", message
        if "already exists" in lowered or "unique" in lowered:
            return "duplicate_entry", message
        if "eligible" in lowered:
            return "ineligible_participant", message
        if "format" in lowered or "invalid" in lowered:
            return "format_error", message
        if "required" in lowered:
            return "missing_required_field", message
        if isinstance(error, ValidationError):
            return "constraint_violation", message
        safe_message = (
            message
            if is_safe_operator_detail(message)
            else "An unexpected error occurred. Please contact your administrator."
        )
        return "unexpected_error", safe_message

    def _execute_row_create(self, row_num, create_row, errors, error_categories):
        """Execute one row-level create callback and record shared failures."""
        if self.dry_run:
            return True
        try:
            create_row()
            return True
        except Exception as error:
            category, message = self._categorize_exception(error)
            self._record_error(errors, error_categories, row_num, category, message)
            return False

    def _build_result_message(
        self, line_count, success_count, error_count, errors, error_categories=None
    ):
        """Build the user-facing result summary for preview and live runs."""
        result_parts = [
            f"Total lines processed: {line_count}",
            f"Successful: {success_count}",
            f"Errors: {error_count}",
        ]

        if self.dry_run:
            result_parts.append("\n*** DRY RUN - No records were created ***")

        if error_categories:
            result_parts.append("\nError categories:")
            for category, count in sorted(error_categories.items()):
                result_parts.append(f"- {category}: {count}")

        if errors:
            result_parts.append("\nErrors:")
            result_parts.extend(errors)

        return "\n".join(result_parts)
