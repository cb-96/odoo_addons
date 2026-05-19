from odoo import models
from odoo.exceptions import ValidationError


class FederationImportTournamentParticipantsWizard(models.TransientModel):
    _name = "federation.import.tournament.participants.wizard"
    _description = "Import Tournament Participants Wizard"
    _inherit = "federation.import.wizard.mixin"

    def _get_import_target_model(self):
        """Return import target model."""
        return "federation.tournament.participant"

    def _get_mapping_guide(self):
        """Return mapping guide."""
        return (
            "Required columns: tournament_code (preferred) or tournament_name, and team_code (preferred) or team_name.\n"
            "Optional columns: seed.\n"
            "Duplicate and eligibility checks reuse the same backend availability rules as manual participant confirmation."
        )

    def action_parse_and_import(self):
        """Execute the parse and import action."""
        self.ensure_one()
        baseline_count = self._prepare_import_execution()
        reader = self._get_csv_reader()
        if not any(
            column in reader.fieldnames
            for column in ("tournament_code", "tournament_name")
        ):
            raise ValidationError(
                "Missing required columns: tournament_code or tournament_name"
            )
        if not any(
            column in reader.fieldnames for column in ("team_code", "team_name")
        ):
            raise ValidationError("Missing required columns: team_code or team_name")

        line_count = 0
        success_count = 0
        error_count = 0
        errors = []
        error_categories = {}

        Participant = self.env["federation.tournament.participant"]
        Tournament = self.env["federation.tournament"]
        Team = self.env["federation.team"]

        for row_num, row in enumerate(reader, start=2):
            line_count += 1
            tournament_code = self._get_row_value(row, "tournament_code")
            tournament_name = self._get_row_value(row, "tournament_name")
            team_code = self._get_row_value(row, "team_code")
            team_name = self._get_row_value(row, "team_name")

            if not (tournament_code or tournament_name):
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "missing_required_field",
                    "Tournament code or tournament name is required.",
                )
                error_count += 1
                continue

            if not (team_code or team_name):
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "missing_required_field",
                    "Team code or team name is required.",
                )
                error_count += 1
                continue

            tournament = False
            if tournament_code:
                tournament = Tournament.search(
                    [("code", "=", tournament_code)], limit=1
                )
            if not tournament and tournament_name:
                tournament = Tournament.search(
                    [("name", "=", tournament_name)], limit=1
                )
            if not tournament:
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "missing_reference",
                    f"Tournament '{tournament_code or tournament_name}' not found.",
                )
                error_count += 1
                continue

            team = False
            if team_code:
                team = Team.search([("code", "=", team_code)], limit=1)
            if not team and team_name:
                team = Team.search([("name", "=", team_name)], limit=1)
            if not team:
                self._record_error(
                    errors,
                    error_categories,
                    row_num,
                    "missing_reference",
                    f"Team '{team_code or team_name}' not found.",
                )
                error_count += 1
                continue

            unavailable_reason = tournament.get_participant_team_unavailability_reason(
                team
            )
            if unavailable_reason:
                category = (
                    "duplicate_entry"
                    if "already exists" in unavailable_reason.lower()
                    else "ineligible_participant"
                )
                self._record_error(
                    errors, error_categories, row_num, category, unavailable_reason
                )
                error_count += 1
                continue

            seed = False
            seed_value = self._get_row_value(row, "seed")
            if seed_value:
                try:
                    seed = int(seed_value)
                except ValueError:
                    self._record_error(
                        errors,
                        error_categories,
                        row_num,
                        "format_error",
                        "Seed must be an integer.",
                    )
                    error_count += 1
                    continue

            if self._execute_row_create(
                row_num,
                lambda: Participant.create(
                    {
                        "tournament_id": tournament.id,
                        "team_id": team.id,
                        "seed": seed or False,
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
