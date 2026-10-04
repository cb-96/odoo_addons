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
        planner = edition.get_competition_planner_data()
        step = "complete" if planner["complete"] else planner["current_step"]
        progress = round(
            100 * sum(item["complete"] for item in planner["steps"])
            / len(planner["steps"])
        )
        labels = {
            "basics": _("Define divisions"),
            "teams": _("Finalize teams"),
            "format": _("Freeze formats"),
            "gamedays": _("Define game days"),
            "schedule": _("Generate schedule"),
            "publication": _("Publish schedule"),
            "complete": _("Setup complete"),
        }
        current_issue = next(
            (item for item in planner["issues"] if item["step"] == step), None
        )
        blocker_hint = current_issue["message"] if current_issue else False
        counts = planner["counts"]
        return {
            "blocker_hint": blocker_hint,
            "step": step,
            "progress": progress,
            "next_action": labels[step],
            "counts": {
                "divisions": counts["divisions"],
                "participants": counts["participants"],
                "gamedays": counts["gamedays"],
                "schedules": counts["schedules"],
                "publications": counts["publications"],
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
            edition.setup_blocker_hint = result["blocker_hint"]
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
