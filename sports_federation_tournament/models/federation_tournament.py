from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..workflow_states import (
    TOURNAMENT_STATE_DRAFT,
    TOURNAMENT_STATE_OPEN,
    TOURNAMENT_STATE_IN_PROGRESS,
    TOURNAMENT_STATE_CLOSED,
    TOURNAMENT_STATE_CANCELLED,
    TOURNAMENT_STATES_ACTIVE,
    TOURNAMENT_STATE_SELECTION,
)


class FederationTournament(models.Model):
    _name = "federation.tournament"
    _description = "Federation Tournament"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, name"

    name = fields.Char(string="Tournament Name", required=True, tracking=True)
    code = fields.Char(string="Code", copy=False)
    category = fields.Selection(
        [
            ("senior", "Senior"),
            ("youth", "Youth"),
            ("junior", "Junior"),
            ("cadet", "Cadet"),
            ("mini", "Mini"),
        ],
        string="Category",
        tracking=True,
    )
    gender = fields.Selection(
        [("male", "Male"), ("female", "Female"), ("mixed", "Mixed")],
        string="Gender",
        tracking=True,
    )
    active = fields.Boolean(default=True)
    date_start = fields.Date(string="Start Date", required=True, tracking=True)
    date_end = fields.Date(string="End Date", tracking=True)
    location = fields.Char(string="Location")
    season_id = fields.Many2one("federation.season", string="Season", tracking=True)
    tournament_type = fields.Selection(
        [
            ("single_day", "Single Day"),
            ("multi_day", "Multi Day"),
        ],
        string="Type",
        default="single_day",
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        TOURNAMENT_STATE_SELECTION,
        string="Status",
        default=TOURNAMENT_STATE_DRAFT,
        required=True,
        tracking=True,
    )
    max_participants = fields.Integer(string="Max Participants", tracking=True)
    edition_id = fields.Many2one(
        "federation.competition.edition",
        string="Competition Edition",
        tracking=True,
        ondelete="set null",
        help="The competition edition (season-specific) this division/tournament belongs to.",
    )
    competition_id = fields.Many2one(
        "federation.competition",
        string="Competition",
        tracking=True,
        ondelete="set null",
    )
    rule_set_id = fields.Many2one(
        "federation.rule.set",
        string="Rule Set",
        tracking=True,
        ondelete="set null",
        help="Competition rules to apply. If set on the linked competition, that rule set is used by default.",
    )
    notes = fields.Text(string="Notes")

    stage_ids = fields.One2many(
        "federation.tournament.stage", "tournament_id", string="Stages"
    )
    participant_ids = fields.One2many(
        "federation.tournament.participant", "tournament_id", string="Participants"
    )
    match_ids = fields.One2many("federation.match", "tournament_id", string="Matches")

    stage_count = fields.Integer(
        string="Stage Count", compute="_compute_counts", store=True
    )
    participant_count = fields.Integer(
        string="Participant Count", compute="_compute_counts", store=True
    )
    match_count = fields.Integer(
        string="Match Count", compute="_compute_counts", store=True
    )

    _code_unique = models.Constraint("unique (code)", "Tournament code must be unique.")

    @api.depends("stage_ids", "participant_ids", "match_ids")
    def _compute_counts(self):
        """Compute counts."""
        for rec in self:
            rec.stage_count = len(rec.stage_ids)
            rec.participant_count = len(rec.participant_ids)
            rec.match_count = len(rec.match_ids)

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        """Validate dates."""
        for rec in self:
            if rec.date_end and rec.date_start and rec.date_end < rec.date_start:
                raise ValidationError("End date must be on or after start date.")

    @api.onchange("edition_id")
    def _onchange_edition_id(self):
        """Handle onchange edition ID."""
        if self.edition_id:
            self.season_id = self.edition_id.season_id
            self.competition_id = self.edition_id.competition_id
            if self.edition_id.rule_set_id and not self.rule_set_id:
                self.rule_set_id = self.edition_id.rule_set_id

    def action_open(self):
        """Execute the open action."""
        invalid_tournaments = self.filtered(
            lambda rec: rec.state != TOURNAMENT_STATE_DRAFT
            or not rec.active
            or not rec.season_id
        )
        if invalid_tournaments:
            raise ValidationError(
                _("Only active draft tournaments linked to a season can be opened.")
            )
        self.write({"state": TOURNAMENT_STATE_OPEN})

    def action_start(self):
        """Execute the start action."""
        invalid_tournaments = self.filtered(
            lambda rec: rec.state != TOURNAMENT_STATE_OPEN
        )
        if invalid_tournaments:
            raise ValidationError(_("Only open tournaments can be started."))

        tournaments_without_stages = self.filtered(lambda rec: not rec.stage_ids)
        if tournaments_without_stages:
            raise ValidationError(
                _("Add at least one stage before starting a tournament.")
            )

        self.write({"state": TOURNAMENT_STATE_IN_PROGRESS})

    def action_close(self):
        """Execute the close action."""
        invalid_tournaments = self.filtered(
            lambda rec: rec.state != TOURNAMENT_STATE_IN_PROGRESS
        )
        if invalid_tournaments:
            raise ValidationError(_("Only tournaments in progress can be closed."))
        self.write({"state": TOURNAMENT_STATE_CLOSED})

    def action_cancel(self):
        """Execute the cancel action."""
        invalid_tournaments = self.filtered(
            lambda rec: rec.state
            not in (
                TOURNAMENT_STATE_DRAFT,
                TOURNAMENT_STATE_OPEN,
                TOURNAMENT_STATE_IN_PROGRESS,
            )
        )
        if invalid_tournaments:
            raise ValidationError(
                _("Only draft, open, or in-progress tournaments can be cancelled.")
            )
        self.write({"state": TOURNAMENT_STATE_CANCELLED})

    def action_draft(self):
        """Execute the draft action."""
        invalid_tournaments = self.filtered(
            lambda rec: rec.state != TOURNAMENT_STATE_CANCELLED
        )
        if invalid_tournaments:
            raise ValidationError(
                _("Only cancelled tournaments can be reset to draft.")
            )
        self.write({"state": TOURNAMENT_STATE_DRAFT})

    def action_archive(self):
        """Execute the archive action."""
        active_tournaments = self.filtered(
            lambda rec: rec.state in TOURNAMENT_STATES_ACTIVE
        )
        if active_tournaments:
            raise ValidationError(
                _("Close or cancel an operational tournament before archiving it.")
            )
        self.write({"active": False})
        return True

    def action_restore(self):
        """Execute the restore action."""
        self.write({"active": True})
        return True

    def action_view_stages(self):
        """Execute the view stages action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_tournament.federation_tournament_stage_action"
        )
        action["domain"] = [("tournament_id", "=", self.id)]
        return action

    def action_view_participants(self):
        """Execute the view participants action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_tournament.federation_tournament_participant_action"
        )
        action["domain"] = [("tournament_id", "=", self.id)]
        return action

    def action_view_matches(self):
        """Execute the view matches action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_tournament.federation_match_action"
        )
        action["domain"] = [("tournament_id", "=", self.id)]
        return action

    def _get_effective_rule_set(self):
        """Return effective rule set."""
        self.ensure_one()
        return self.rule_set_id or (
            self.competition_id.rule_set_id
            if self.competition_id
            else self.env["federation.rule.set"]
        )

    def _get_rule_set_allowed_team_values(self):
        """Return rule set allowed team values."""
        self.ensure_one()
        rule_set = self._get_effective_rule_set()
        if not rule_set:
            return set()

        rules = rule_set.eligibility_rule_ids.filtered(
            lambda rule: rule.eligibility_type == "gender"
            and rule.active
            and not rule.is_placeholder
        )
        allowed = set()
        for rule in rules:
            if rule.allowed_categories:
                allowed.update(
                    value.strip().lower()
                    for value in rule.allowed_categories.split(",")
                    if value.strip()
                )
        return allowed

    def get_allowed_team_domain(self):
        """Return an Odoo search domain for teams that may be eligible.

        This is used for backend field domains. Exact validation still goes
        through ``get_team_eligibility_error``.
        """
        self.ensure_one()
        domain = []
        if self.gender:
            domain.append(("gender", "=", self.gender))
        if self.category:
            domain.append(("category", "=", self.category))

        allowed = sorted(self._get_rule_set_allowed_team_values())
        if allowed:
            domain.extend(["|", ("gender", "in", allowed), ("category", "in", allowed)])
        return domain

    def search_eligible_teams(self, extra_domain=None):
        """Handle search eligible teams."""
        self.ensure_one()
        snapshot = self.get_team_selection_snapshot(extra_domain=extra_domain)
        return snapshot["available_teams"]

    def get_team_selection_snapshot(
        self, extra_domain=None, blocked_reason_by_team_id=None
    ):
        """Return selectable teams plus explicit exclusion reasons.

        ``blocked_reason_by_team_id`` is used for non-eligibility exclusions,
        such as duplicate registrations or existing participant records.
        """
        self.ensure_one()
        Team = self.env["federation.team"]
        teams = Team.search(list(extra_domain or []), order="name")
        blocked_reason_by_team_id = blocked_reason_by_team_id or {}

        available_team_ids = []
        excluded_teams = []
        for team in teams:
            blocked_reason = blocked_reason_by_team_id.get(team.id)
            if blocked_reason:
                excluded_teams.append({"team": team, "reason": blocked_reason})
                continue

            error = self.get_team_eligibility_error(team)
            if error:
                excluded_teams.append({"team": team, "reason": error})
                continue

            available_team_ids.append(team.id)

        return {
            "available_teams": Team.browse(available_team_ids),
            "excluded_teams": excluded_teams,
        }

    def _get_existing_participant_reason(self):
        """Return existing participant reason."""
        self.ensure_one()
        return _("A participant record already exists for this team.")

    def _get_participant_blocked_reason_by_team_id(self, current_participant=None):
        """Return participant blocked reason by team ID."""
        self.ensure_one()
        domain = [("tournament_id", "=", self.id)]
        if current_participant and current_participant.id:
            domain.append(("id", "!=", current_participant.id))

        existing = self.env["federation.tournament.participant"].search(domain)
        blocked_reason = self._get_existing_participant_reason()
        return {
            record.team_id.id: blocked_reason for record in existing if record.team_id
        }

    def get_participant_team_selection_snapshot(
        self, extra_domain=None, current_participant=None
    ):
        """Return participant team selection snapshot."""
        self.ensure_one()
        return self.get_team_selection_snapshot(
            extra_domain=extra_domain,
            blocked_reason_by_team_id=self._get_participant_blocked_reason_by_team_id(
                current_participant=current_participant
            ),
        )

    def get_participant_team_unavailability_reason(
        self, team, current_participant=None
    ):
        """Return participant team unavailability reason."""
        self.ensure_one()
        blocked_reason = self._get_participant_blocked_reason_by_team_id(
            current_participant=current_participant
        ).get(team.id)
        if blocked_reason:
            return blocked_reason
        return self.get_team_eligibility_error(team)

    def get_team_eligibility_error(self, team):
        """Return a human-readable reason when a team cannot register.

        This is the central source of truth for team-vs-tournament checks so
        portal registration, backend registration, and direct participant
        creation all behave consistently.
        """
        self.ensure_one()
        if not team:
            return _("A team must be selected.")

        if self.gender and (team.gender or "").lower() != self.gender.lower():
            return _(
                "Team '%(team)s' (gender=%(team_gender)s) is not eligible for tournament '%(tournament)s' (gender=%(tournament_gender)s)."
            ) % {
                "team": team.name,
                "team_gender": team.gender or _("not set"),
                "tournament": self.name,
                "tournament_gender": self.gender,
            }

        if self.category and (team.category or "").lower() != self.category.lower():
            return _(
                "Team '%(team)s' (category=%(team_category)s) is not eligible for tournament '%(tournament)s' (category=%(tournament_category)s)."
            ) % {
                "team": team.name,
                "team_category": team.category or _("not set"),
                "tournament": self.name,
                "tournament_category": self.category,
            }

        rule_set = self._get_effective_rule_set()
        if not rule_set:
            return False

        allowed = self._get_rule_set_allowed_team_values()
        if not allowed:
            return False

        team_gender = (team.gender or "").lower()
        team_category = (team.category or "").lower()
        if allowed and team_gender not in allowed and team_category not in allowed:
            return _(
                "Team '%(team)s' (category=%(team_category)s, gender=%(team_gender)s) is not eligible for tournament '%(tournament)s' according to rule set '%(rule_set)s'."
            ) % {
                "team": team.name,
                "team_category": team.category or _("not set"),
                "team_gender": team.gender or _("not set"),
                "tournament": self.name,
                "rule_set": rule_set.name,
            }
        return False

    def is_team_allowed(self, team):
        """Return True when the team passes the tournament eligibility checks."""
        self.ensure_one()
        return not self.get_team_eligibility_error(team)
