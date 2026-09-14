from odoo import _, models


class FederationCompetitionSetupReadiness(models.AbstractModel):
    _name = "federation.competition.setup.readiness"
    _description = "Competition Setup Readiness"

    def evaluate(self, edition):
        """Return the single operator-facing setup assessment.

        Technical models retain their own lifecycle states. This projection only
        decides where the operator should continue and must not mutate them.
        """
        edition.ensure_one()
        divisions, participants, gamedays, schedules, publications = (
            edition._setup_counts()
        )
        if not divisions:
            step, progress = "divisions", 10
        elif not participants:
            step, progress = "participants", 30
        elif not gamedays:
            step, progress = "gamedays", 50
        elif not schedules:
            step, progress = "schedule", 70
        elif not publications:
            step, progress = "publication", 90
        else:
            step, progress = "complete", 100
        labels = {
            "divisions": _("Define divisions"),
            "participants": _("Add teams"),
            "gamedays": _("Define game days"),
            "schedule": _("Generate schedule"),
            "publication": _("Publish schedule"),
            "complete": _("Setup complete"),
        }
        return {
            "step": step,
            "progress": progress,
            "next_action": labels[step],
            "counts": {
                "divisions": divisions,
                "participants": participants,
                "gamedays": gamedays,
                "schedules": schedules,
                "publications": publications,
            },
        }


class FederationCompetitionEditionCanonicalSetup(models.Model):
    _inherit = "federation.competition.edition"

    def _compute_setup_guidance(self):
        readiness_service = self.env["federation.competition.setup.readiness"]
        for edition in self:
            result = readiness_service.evaluate(edition)
            counts = result["counts"]
            edition.setup_step = result["step"]
            edition.setup_progress = result["progress"]
            edition.setup_next_action = result["next_action"]
            edition.setup_division_count = counts["divisions"]
            edition.setup_participant_count = counts["participants"]
            edition.setup_gameday_count = counts["gamedays"]
            edition.setup_schedule_count = counts["schedules"]
            edition.setup_publication_count = counts["publications"]
            edition.setup_summary = _(
                "%(divisions)s divisions, %(participants)s teams, "
                "%(gamedays)s game days, %(schedules)s schedules and "
                "%(publications)s live publications.",
                **counts,
            )
