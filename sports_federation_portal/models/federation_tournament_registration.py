from markupsafe import escape

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class FederationTournamentRegistration(models.Model):
    """Tournament registration request submitted by portal users.

    This model captures the portal-side registration intent. Federation
    staff reviews submissions and, upon confirmation, the system can
    optionally create a ``federation.tournament.participant`` record.

    Workflow: draft -> submitted -> confirmed / rejected / cancelled
    """

    _name = "federation.tournament.registration"
    _description = "Tournament Registration Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(
        string="Reference",
        readonly=True,
        copy=False,
        default="New",
    )
    tournament_id = fields.Many2one(
        "federation.tournament",
        string="Tournament",
        required=True,
        tracking=True,
        ondelete="cascade",
    )
    team_id = fields.Many2one(
        "federation.team",
        string="Team",
        required=True,
        tracking=True,
        ondelete="restrict",
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
    season_id = fields.Many2one(
        "federation.season",
        string="Season",
        related="tournament_id.season_id",
        store=True,
        readonly=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Submitted By",
        default=lambda self: self.env.user,
        readonly=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        related="user_id.partner_id",
        store=True,
        readonly=True,
    )
    registration_date = fields.Date(
        string="Registration Date",
        default=fields.Date.context_today,
        required=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("confirmed", "Confirmed"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
    )
    notes = fields.Text(string="Notes")
    rejection_reason = fields.Text(
        string="Rejection Reason",
        readonly=True,
        tracking=True,
    )
    participant_id = fields.Many2one(
        "federation.tournament.participant",
        string="Linked Participant",
        readonly=True,
        copy=False,
        ondelete="set null",
    )

    _team_tournament_unique = models.Constraint(
        "UNIQUE(team_id, tournament_id)",
        "A team can only submit one registration request per tournament.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        if isinstance(vals_list, dict):
            vals_list = [vals_list]

        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = (
                    self.env["ir.sequence"]
                    .sudo()
                    .next_by_code("federation.tournament.registration")
                    or "New"
                )
        return super().create(vals_list)

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
            selection_snapshot = rec.tournament_id.get_team_selection_snapshot(
                blocked_reason_by_team_id=rec._get_blocked_team_reason_by_team_id()
            )
            rec.available_team_ids = selection_snapshot["available_teams"]
            rec.excluded_team_feedback_html = rec._render_excluded_team_feedback_html(
                selection_snapshot["excluded_teams"]
            )

    def _get_blocked_team_reason_by_team_id(self):
        """Return blocked team reason by team ID."""
        self.ensure_one()
        if not self.tournament_id:
            return {}

        domain = [
            ("tournament_id", "=", self.tournament_id.id),
            ("state", "!=", "cancelled"),
        ]
        if self.id:
            domain.append(("id", "!=", self.id))

        existing = self.search(domain)
        return {
            record.team_id.id: _("Already registered or currently awaiting review.")
            for record in existing
            if record.team_id
        }

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
        blocked_reason = self._get_blocked_team_reason_by_team_id().get(team.id)
        if blocked_reason:
            return blocked_reason
        return self.tournament_id.get_team_eligibility_error(team)

    @api.model
    def _portal_submit_registration_request(
        self, tournament, team, notes=None, user=None
    ):
        """Create and submit a portal-managed tournament registration request."""
        user = user or self.env.user
        PortalPrivilege = self.env["federation.portal.privilege"]
        tournament = PortalPrivilege.elevate(tournament, user=user)
        team = PortalPrivilege.elevate(team, user=user)
        if not tournament.exists() or tournament.state != "open":
            raise ValidationError(
                _("This tournament is not currently open for registrations.")
            )
        if not team.exists():
            raise ValidationError(_("Select a valid team before continuing."))

        clubs = PortalPrivilege.elevate(
            self.env["federation.club.representative"],
            user=user,
        )._get_clubs_for_user(user=user)
        if team.club_id not in clubs:
            raise AccessError(_("You can only register your own teams."))

        eligibility_error = tournament.get_team_eligibility_error(team)
        if eligibility_error:
            raise ValidationError(eligibility_error)

        existing = PortalPrivilege.portal_search(
            self,
            [
                ("tournament_id", "=", tournament.id),
                ("team_id", "=", team.id),
                ("state", "!=", "cancelled"),
            ],
            limit=1,
            user=user,
        )
        if existing:
            raise ValidationError(_("This team is already registered."))

        if tournament.max_participants > 0:
            current_count = PortalPrivilege.portal_search_count(
                self.env["federation.tournament.participant"],
                [
                    ("tournament_id", "=", tournament.id),
                    ("state", "!=", "withdrawn"),
                ],
                user=user,
            )
            pending_count = PortalPrivilege.portal_search_count(
                self,
                [
                    ("tournament_id", "=", tournament.id),
                    ("state", "=", "submitted"),
                ],
                user=user,
            )
            if current_count + pending_count >= tournament.max_participants:
                raise ValidationError(_("Tournament is full"))

        registration = PortalPrivilege.portal_create(
            self,
            {
                "tournament_id": tournament.id,
                "team_id": team.id,
                "notes": (notes or "").strip() or False,
                "user_id": user.id,
            },
            user=user,
        )
        PortalPrivilege.portal_call(
            registration,
            "action_submit",
            scope_domain=[
                ("team_id", "=", team.id),
                ("tournament_id", "=", tournament.id),
            ],
            user=user,
        )
        return registration

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

    @api.constrains("team_id", "club_id")
    def _check_portal_ownership(self):
        """Ensure that when created via portal, the team belongs to the
        submitting user's club."""
        for rec in self:
            if rec.user_id and rec.team_id and rec.club_id:
                rep = self.env["federation.club.representative"].search(
                    [
                        ("user_id", "=", rec.user_id.id),
                        ("club_id", "=", rec.club_id.id),
                    ],
                    limit=1,
                )
                if not rep and not rec.user_id.has_group(
                    "sports_federation_base.group_federation_manager"
                ):
                    raise ValidationError(
                        "You can only register teams that belong to your club."
                    )

    @api.constrains("team_id", "tournament_id")
    def _check_team_category_gender(self):
        """Ensure the team is eligible for the selected tournament."""
        for rec in self:
            if not rec.team_id or not rec.tournament_id:
                continue
            error = rec.tournament_id.get_team_eligibility_error(rec.team_id)
            if error:
                raise ValidationError(error)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_submit(self):
        """Submit the registration for review."""
        for rec in self:
            if rec.state != "draft":
                raise ValidationError("Only draft registrations can be submitted.")
            rec.state = "submitted"

    def action_confirm(self):
        """Confirm the registration and optionally create a participant."""
        for rec in self:
            if rec.state != "submitted":
                raise ValidationError("Only submitted registrations can be confirmed.")
            rec.state = "confirmed"
            # Create participant record if one does not already exist
            if not rec.participant_id:
                existing = self.env["federation.tournament.participant"].search(
                    [
                        ("tournament_id", "=", rec.tournament_id.id),
                        ("team_id", "=", rec.team_id.id),
                    ],
                    limit=1,
                )
                if existing:
                    rec.participant_id = existing.id
                else:
                    participant = self.env["federation.tournament.participant"].create(
                        {
                            "tournament_id": rec.tournament_id.id,
                            "team_id": rec.team_id.id,
                            "registration_date": rec.registration_date,
                            "state": "registered",
                        }
                    )
                    rec.participant_id = participant.id

    def action_reject(self, reason=None):
        """Reject the registration with an optional reason."""
        for rec in self:
            if rec.state != "submitted":
                raise ValidationError("Only submitted registrations can be rejected.")
            rec.state = "rejected"
            if reason:
                rec.rejection_reason = reason

    def action_cancel(self):
        """Cancel the registration (portal or backend)."""
        for rec in self:
            if rec.state in ("confirmed",):
                raise ValidationError("Confirmed registrations cannot be cancelled.")
            rec.state = "cancelled"

    def action_reset_draft(self):
        """Reset to draft (backend only)."""
        for rec in self:
            rec.state = "draft"

    def action_view_participant(self):
        """Execute the view participant action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_tournament.federation_tournament_participant_action"
        )
        action["res_id"] = self.participant_id.id
        action["views"] = [(False, "form")]
        return action
