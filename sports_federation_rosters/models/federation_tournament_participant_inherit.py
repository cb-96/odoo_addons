from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FederationTournamentParticipant(models.Model):
    _inherit = "federation.tournament.participant"

    confirmation_blocking = fields.Boolean(
        compute="_compute_confirmation_readiness",
        string="Confirmation Blocking",
    )
    confirmation_warning = fields.Boolean(
        compute="_compute_confirmation_readiness",
        string="Confirmation Warning",
    )

    ready_for_confirmation = fields.Boolean(
        compute="_compute_confirmation_readiness",
        string="Roster Deadline Satisfied",
    )
    roster_deadline_date = fields.Date(
        compute="_compute_confirmation_readiness",
        string="Roster Deadline",
    )
    readiness_roster_id = fields.Many2one(
        "federation.team.roster",
        compute="_compute_confirmation_readiness",
        string="Team Roster",
    )
    confirmation_feedback = fields.Text(
        compute="_compute_confirmation_readiness",
        string="Roster Feedback",
    )

    @api.depends(
        "team_id",
        "tournament_id",
        "tournament_id.season_id",
        "tournament_id.date_start",
        "tournament_id.competition_id",
        "tournament_id.match_ids.date_scheduled",
        "tournament_id.match_ids.home_team_id",
        "tournament_id.match_ids.away_team_id",
        "state",
    )
    def _compute_confirmation_readiness(self):
        """Compute confirmation readiness."""
        for record in self:
            assessment = record._get_roster_assessment()
            blocking_issues = bool(assessment["blocking_issues"])
            deadline_reached = bool(assessment["deadline_reached"])
            record.ready_for_confirmation = not bool(assessment["blocking_issues"])
            record.confirmation_blocking = blocking_issues and deadline_reached
            record.confirmation_warning = blocking_issues and not deadline_reached
            record.roster_deadline_date = assessment["deadline_date"] or False
            record.readiness_roster_id = (
                assessment["roster"].id if assessment["roster"] else False
            )
            record.confirmation_feedback = assessment["feedback"]

    def _get_readiness_roster(self):
        """Return readiness roster."""
        self.ensure_one()
        if not self.team_id or not self.tournament_id:
            return self.env["federation.team.roster"]
        return self.team_id._get_tournament_roster_assessment(self.tournament_id)[
            "roster"
        ]

    def _get_roster_assessment(self, today=None):
        """Return roster assessment."""
        self.ensure_one()
        if not self.team_id or not self.tournament_id:
            return {
                "roster": self.env["federation.team.roster"],
                "first_match_date": False,
                "deadline_date": False,
                "deadline_reached": False,
                "blocking_issues": [],
                "feedback": False,
            }
        return self.team_id._get_tournament_roster_assessment(
            self.tournament_id,
            today=today,
        )

    def _ensure_linked_roster(self):
        """Handle ensure linked roster."""
        for record in self.filtered(
            lambda participant: participant.team_id
            and participant.tournament_id
            and participant.tournament_id.season_id
        ):
            record.team_id._ensure_tournament_roster(record.tournament_id)

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        records = super().create(vals_list)
        records._ensure_linked_roster()
        return records

    def write(self, vals):
        """Update records with module-specific side effects."""
        result = super().write(vals)
        if {"team_id", "tournament_id"}.intersection(vals):
            self._ensure_linked_roster()
        return result

    def _get_confirmation_deadline_errors(self):
        """Return operator-facing confirmation blockers once the roster deadline hits."""
        errors = []
        for record in self:
            assessment = record._get_roster_assessment()
            if assessment["blocking_issues"]:
                feedback = assessment["feedback"] or "; ".join(
                    assessment["blocking_issues"]
                )
                errors.append(
                    _("%(team)s: %(feedback)s")
                    % {
                        "team": record.team_id.display_name or record.display_name,
                        "feedback": feedback,
                    }
                )
        return errors

    def action_open_readiness_roster(self):
        """Open the roster that controls this participant's confirmation readiness."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_rosters.action_federation_team_roster"
        )
        domain = []
        context = {}
        if self.team_id:
            domain.append(("team_id", "=", self.team_id.id))
            context["default_team_id"] = self.team_id.id

        season = self.tournament_id.season_id
        if season:
            domain.append(("season_id", "=", season.id))
            context["default_season_id"] = season.id

        if self.tournament_id.competition_id:
            domain.append(("competition_id", "=", self.tournament_id.competition_id.id))
            context["default_competition_id"] = self.tournament_id.competition_id.id

        roster = self._get_readiness_roster()
        if roster:
            action.update(
                {
                    "view_mode": "form",
                    "res_id": roster.id,
                    "domain": [],
                }
            )
        else:
            action["domain"] = domain
        action["context"] = context
        return action

    def action_confirm(self):
        """Execute the confirm action."""
        self._ensure_linked_roster()
        deadline_errors = self._get_confirmation_deadline_errors()
        if deadline_errors:
            raise ValidationError(
                _(
                    "Participants cannot be confirmed after the roster deadline until each team has an active ready roster:\n- %(errors)s"
                )
                % {"errors": "\n- ".join(deadline_errors)}
            )
        return super().action_confirm()
