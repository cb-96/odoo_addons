from markupsafe import escape

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationTournamentParticipant(models.Model):
    _name = "federation.tournament.participant"
    _description = "Tournament Participant"
    _order = "name"

    name = fields.Char(string="Name", compute="_compute_name", store=True)
    tournament_id = fields.Many2one(
        "federation.tournament", string="Tournament", required=True, ondelete="cascade"
    )
    team_id = fields.Many2one(
        "federation.team", string="Team", required=True, ondelete="restrict"
    )
    eligible_team_ids = fields.Many2many(
        "federation.team",
        string="Eligible Teams",
        compute="_compute_team_selection",
    )
    available_team_ids = fields.Many2many(
        "federation.team",
        string="Available Teams",
        compute="_compute_team_selection",
    )
    excluded_team_feedback_html = fields.Html(
        string="Unavailable Teams",
        compute="_compute_team_selection",
    )
    club_id = fields.Many2one(
        "federation.club",
        string="Club",
        related="team_id.club_id",
        store=True,
        readonly=True,
    )
    stage_id = fields.Many2one(
        "federation.tournament.stage", string="Stage", ondelete="set null"
    )
    group_id = fields.Many2one(
        "federation.tournament.group", string="Group", ondelete="set null"
    )
    seed = fields.Integer(string="Seed")
    registration_date = fields.Date(
        string="Registration Date", default=fields.Date.context_today
    )
    state = fields.Selection(
        [
            ("registered", "Registered"),
            ("confirmed", "Confirmed"),
            ("withdrawn", "Withdrawn"),
        ],
        string="Status",
        default="registered",
        required=True,
    )
    notes = fields.Text(string="Notes")

    _team_tournament_unique = models.Constraint(
        "unique (team_id, tournament_id)",
        "A team can only participate once per tournament.",
    )

    @api.depends("team_id", "tournament_id")
    def _compute_name(self):
        """Compute name."""
        for rec in self:
            if rec.team_id and rec.tournament_id:
                rec.name = f"{rec.team_id.name} @ {rec.tournament_id.name}"
            else:
                rec.name = "New"

    @api.depends("tournament_id", "team_id")
    def _compute_team_selection(self):
        """Compute team selection."""
        Team = self.env["federation.team"]
        for rec in self:
            if not rec.tournament_id:
                rec.eligible_team_ids = Team.browse([])
                rec.available_team_ids = Team.browse([])
                rec.excluded_team_feedback_html = False
                continue

            rec.eligible_team_ids = rec.tournament_id.search_eligible_teams()
            selection_snapshot = (
                rec.tournament_id.get_participant_team_selection_snapshot(
                    current_participant=rec
                )
            )
            rec.available_team_ids = selection_snapshot["available_teams"]
            rec.excluded_team_feedback_html = rec._render_excluded_team_feedback_html(
                selection_snapshot["excluded_teams"]
            )

    def _render_excluded_team_feedback_html(self, excluded_teams):
        """Handle render excluded team feedback HTML."""
        if not excluded_teams:
            return False

        intro = escape(
            _("Only teams that can currently be selected appear in the Team dropdown.")
        )
        items = "".join(
            "<li><strong>{team}</strong> ({club}): {reason}</li>".format(
                team=escape(item["team"].name),
                club=escape(item["team"].club_id.display_name or _("No Club")),
                reason=escape(item["reason"]),
            )
            for item in excluded_teams
        )
        return f"<p>{intro}</p><ul>{items}</ul>"

    def _get_team_unavailability_reason(self, team):
        """Return team unavailability reason."""
        self.ensure_one()
        return self.tournament_id.get_participant_team_unavailability_reason(
            team,
            current_participant=self,
        )

    @api.onchange("tournament_id")
    def _onchange_tournament_id(self):
        """Handle onchange tournament ID."""
        domain = [("id", "in", self.available_team_ids.ids)]
        if (
            self.team_id
            and self.tournament_id
            and self.team_id not in self.available_team_ids
        ):
            warning = {
                "title": _("Ineligible Team"),
                "message": self._get_team_unavailability_reason(self.team_id),
            }
            self.team_id = False
            return {"domain": {"team_id": domain}, "warning": warning}
        return {"domain": {"team_id": domain}}

    @api.constrains("team_id", "tournament_id")
    def _check_team_eligibility(self):
        """Validate team eligibility."""
        for rec in self:
            if not rec.team_id or not rec.tournament_id:
                continue
            error = rec.tournament_id.get_team_eligibility_error(rec.team_id)
            if error:
                raise ValidationError(error)

    def action_confirm(self):
        """Execute the confirm action."""
        for rec in self:
            rec.state = "confirmed"
            Dispatcher = rec.env.get("federation.notification.dispatcher")
            if Dispatcher is not None:
                Dispatcher.send_participant_confirmed(rec)

    def action_withdraw(self):
        """Execute the withdraw action."""
        for rec in self:
            rec.state = "withdrawn"
