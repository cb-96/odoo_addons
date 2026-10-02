from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationCompetitionEditionSetup(models.Model):
    _inherit = "federation.competition.edition"

    setup_step = fields.Selection(
        [
            ("divisions", "Define divisions"),
            ("participants", "Add teams"),
            ("gamedays", "Define game days"),
            ("schedule", "Generate schedule"),
            ("publication", "Publish schedule"),
            ("complete", "Setup complete"),
        ],
        compute="_compute_setup_guidance",
    )
    setup_progress = fields.Integer(compute="_compute_setup_guidance")
    setup_next_action = fields.Char(compute="_compute_setup_guidance")
    setup_blocker_hint = fields.Char(compute="_compute_setup_guidance")
    setup_summary = fields.Text(compute="_compute_setup_guidance")
    setup_division_count = fields.Integer(compute="_compute_setup_guidance")
    setup_participant_count = fields.Integer(compute="_compute_setup_guidance")
    setup_gameday_count = fields.Integer(compute="_compute_setup_guidance")
    setup_schedule_count = fields.Integer(compute="_compute_setup_guidance")
    setup_publication_count = fields.Integer(compute="_compute_setup_guidance")

    def _setup_counts(self):
        self.ensure_one()
        Tournament = self.env["federation.tournament"]
        Matchday = self.env["federation.matchday"]
        Schedule = self.env["federation.schedule"]
        divisions = Tournament.search([("edition_id", "=", self.id)])
        participant_count = 0
        if "federation.participant.set" in self.env:
            participant_sets = self.env["federation.participant.set"].search(
                [("edition_id", "=", self.id), ("state", "=", "finalized")]
            )
            participant_count = len(participant_sets.mapped("line_ids.team_id"))
        gamedays = Matchday.search_count([("edition_id", "=", self.id)])
        schedules = Schedule.search([("edition_id", "=", self.id)])
        publications = 0
        if "federation.schedule.publication" in self.env:
            publications = self.env["federation.schedule.publication"].search_count(
                [("edition_id", "=", self.id), ("state", "=", "live")]
            )
        return len(divisions), participant_count, gamedays, len(schedules), publications

    def action_continue_setup(self):
        self.ensure_one()
        assessment = self.env["federation.competition.setup.readiness"].evaluate(self)
        actions = {
            "divisions": self.action_setup_divisions,
            "participants": self.action_setup_participants,
            "gamedays": self.action_setup_gamedays,
            "schedule": self.action_setup_schedule,
            "publication": self.action_setup_publication,
        }
        # Completed setup has no blocker; remain on the edition rather than
        # sending the operator back to game-day creation.
        if assessment["step"] == "complete":
            return self.get_formview_action()
        return actions[assessment["step"]]()

    def _action_with_edition(self, xmlid, **extra_context):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(xmlid)
        context = dict(self.env.context)
        context.update(
            {
                "default_edition_id": self.id,
                "search_default_edition_id": self.id,
                "active_model": self._name,
                "active_id": self.id,
                "active_ids": self.ids,
            }
        )
        context.update(extra_context)
        action["context"] = context
        return action

    def action_setup_divisions(self):
        self.ensure_one()
        action = self.action_view_tournaments()
        action["context"] = dict(
            self.env.context,
            default_edition_id=self.id,
            default_season_id=self.season_id.id,
            default_rule_set_id=self.rule_set_id.id,
        )
        action["domain"] = [("edition_id", "=", self.id)]
        return action

    def action_setup_participants(self):
        action = self._action_with_edition(
            "sports_federation_registration.action_registration_desk"
        )
        action["domain"] = [("edition_id", "=", self.id)]
        return action

    def action_setup_gamedays(self):
        self.ensure_one()
        wizard = self.env["federation.competition.gameday.setup.wizard"].create(
            {"edition_id": self.id}
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Define Game Days"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_setup_schedule(self):
        return self._action_with_edition(
            "sports_federation_scheduling.action_competition_schedule_wizard"
        )

    def action_setup_publication(self):
        return self._action_with_edition(
            "sports_federation_schedule_approval.action_schedule_review_queue",
            search_default_pending=1,
        )
