from odoo import _, fields, models
from odoo.exceptions import ValidationError


class FederationCompetitionEditionSetup(models.Model):
    _inherit = "federation.competition.edition"

    setup_step = fields.Selection(
        [
            ("basics", "Define divisions"),
            ("teams", "Finalize teams"),
            ("format", "Freeze formats"),
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
        schedules = Schedule.search(
            [("edition_id", "=", self.id), ("state", "!=", "superseded")]
        )
        publications = 0
        if "current_publication_id" in Matchday._fields:
            publications = Matchday.search_count(
                [
                    ("edition_id", "=", self.id),
                    ("current_publication_id.state", "=", "live"),
                ]
            )
        return len(divisions), participant_count, gamedays, len(schedules), publications

    def action_continue_setup(self):
        self.ensure_one()
        assessment = self.env["federation.competition.setup.readiness"].evaluate(self)
        actions = {
            "basics": self.action_setup_divisions,
            "teams": self.action_setup_participants,
            "format": self.action_setup_format,
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
        self.ensure_one()
        finalized_divisions = self.env["federation.participant.set"].search(
            [("edition_id", "=", self.id), ("state", "=", "finalized")]
        ).mapped("division_id")
        division = (self.tournament_ids - finalized_divisions).sorted(
            lambda item: (item.name or "", item.id)
        )[:1] or self.tournament_ids.sorted(lambda item: (item.name or "", item.id))[:1]
        if not division:
            return self.action_setup_divisions()
        wizard = self.env["federation.competition.team.selection.wizard"].create(
            {"edition_id": self.id, "division_id": division.id}
        )
        wizard._onchange_division_id()
        return {
            "type": "ir.actions.act_window",
            "name": _("Select Teams"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
        }

    def action_setup_format(self):
        self.ensure_one()
        structures = self.env["federation.competition.structure"].search(
            [("edition_id", "=", self.id), ("state", "=", "frozen")]
        )
        division = (self.tournament_ids - structures.mapped("division_id")).sorted(
            lambda item: (item.name or "", item.id)
        )[:1] or self.tournament_ids.sorted(lambda item: (item.name or "", item.id))[:1]
        if not division:
            return self.action_setup_divisions()
        participant_set = self.env["federation.participant.set"].search(
            [
                ("edition_id", "=", self.id),
                ("division_id", "=", division.id),
                ("state", "=", "finalized"),
            ],
            order="id desc",
            limit=1,
        )
        if not participant_set:
            return self.action_setup_participants()
        wizard = self.env["federation.competition.format.setup.wizard"].create(
            {
                "edition_id": self.id,
                "division_id": division.id,
                "participant_set_id": participant_set.id,
                "format_type": self.setup_default_format_type,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Choose Format"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
        }

    def action_setup_gamedays(self):
        self.ensure_one()
        wizard = self.env["federation.competition.gameday.setup.wizard"].create(
            {
                "edition_id": self.id,
                "new_date": self.date_start or fields.Date.context_today(self),
                "default_venue_id": self.setup_default_venue_id.id,
                "default_start_hour": self.setup_default_start_hour,
                "default_end_hour": self.setup_default_end_hour,
                "default_slot_duration_minutes": self.setup_default_slot_duration_minutes,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Define Game Days"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }

    def action_setup_schedule(self):
        self.ensure_one()
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {"edition_id": self.id}
        )
        wizard._onchange_edition_id()
        return {
            "type": "ir.actions.act_window",
            "name": _("Plan Competition"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
            "context": dict(
                self.env.context,
                competition_planner_edition_id=self.id,
                return_to_competition_workspace=True,
            ),
        }

    def action_setup_publication(self):
        return self._action_with_edition(
            "sports_federation_schedule_approval.action_schedule_review_queue",
            search_default_pending=1,
        )
