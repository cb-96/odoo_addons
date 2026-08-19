from odoo import _, api, models
from odoo.exceptions import ValidationError


class FederationCompetitionIntegrityService(models.AbstractModel):
    _name = "federation.competition.integrity.service"
    _description = "Competition Integrity Service"

    @api.model
    def scan_division(self, division_id):
        division = self.env["federation.tournament"].browse(int(division_id)).exists()
        if not division:
            raise ValidationError(_("The selected division does not exist."))
        issues = []
        stage_ids = set(division.stage_ids.ids)

        def add(code, message, records=None, severity="blocking"):
            records = records or self.env["federation.tournament"].browse()
            issues.append(
                {
                    "code": code,
                    "severity": severity,
                    "message": message,
                    "model": records._name if records else False,
                    "record_ids": records.ids if records else [],
                }
            )

        foreign_matches = division.match_ids.filtered(
            lambda match: match.stage_id and match.stage_id.id not in stage_ids
        )
        if foreign_matches:
            add(
                "foreign_match_stage",
                _("Matches reference a stage outside this division."),
                foreign_matches,
            )

        foreign_gamedays = division.round_ids.filtered(
            lambda day: day.stage_id and day.stage_id.id not in stage_ids
        )
        if foreign_gamedays:
            add(
                "foreign_gameday_stage",
                _("Gamedays reference a stage outside this division."),
                foreign_gamedays,
            )

        Progression = self.env["federation.stage.progression"]
        progressions = Progression.search([("tournament_id", "=", division.id)])
        foreign_progressions = progressions.filtered(
            lambda rule: rule.source_stage_id.id not in stage_ids
            or rule.target_stage_id.id not in stage_ids
        )
        if foreign_progressions:
            add(
                "foreign_progression_stage",
                _("Progression rules leave the division stage graph."),
                foreign_progressions,
            )

        self_cycles = progressions.filtered(
            lambda rule: rule.source_stage_id == rule.target_stage_id
        )
        if self_cycles:
            add(
                "progression_self_cycle",
                _("A progression rule targets its own source stage."),
                self_cycles,
            )

        if (
            division.workspace_stage_id
            and division.workspace_stage_id.id not in stage_ids
        ):
            add(
                "invalid_workspace_stage",
                _("The default workspace stage is outside this division."),
            )
        if (
            division.workspace_knockout_stage_id
            and division.workspace_knockout_stage_id.id not in stage_ids
        ):
            add(
                "invalid_knockout_stage",
                _("The default knockout stage is outside this division."),
            )

        duplicate_teams = []
        seen = set()
        for participant in division.participant_ids.filtered("team_id"):
            if participant.team_id.id in seen:
                duplicate_teams.append(participant.id)
            seen.add(participant.team_id.id)
        if duplicate_teams:
            add(
                "duplicate_participant",
                _("A team occurs more than once in this division."),
                self.env["federation.tournament.participant"].browse(duplicate_teams),
            )

        return {
            "division_id": division.id,
            "valid": not any(issue["severity"] == "blocking" for issue in issues),
            "issues": issues,
            "issue_count": len(issues),
        }

    @api.model
    def assert_division_integrity(self, division_id):
        result = self.scan_division(division_id)
        if not result["valid"]:
            messages = "\n".join(
                "- %s" % issue["message"] for issue in result["issues"]
            )
            raise ValidationError(
                _("Competition integrity checks failed:\n%(issues)s", issues=messages)
            )
        return result

    @api.model
    def scan_active_divisions(self):
        divisions = self.env["federation.tournament"].search(
            [
                ("workspace_state", "not in", ("archived", "cancelled")),
            ]
        )
        return [self.scan_division(division.id) for division in divisions]
