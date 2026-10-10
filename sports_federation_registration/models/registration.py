from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationRegistrationWindow(models.Model):
    _name = "federation.registration.window"
    _description = "Competition Registration Window"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    name = fields.Char(required=True)
    edition_id = fields.Many2one(
        "federation.competition.edition", required=True, ondelete="cascade", index=True
    )
    division_id = fields.Many2one(
        "federation.tournament", required=True, ondelete="cascade", index=True
    )
    date_open = fields.Datetime()
    date_close = fields.Datetime()
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("open", "Open"),
            ("closed", "Closed"),
            ("finalized", "Finalized"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    entry_ids = fields.One2many("federation.competition.entry", "window_id")
    participant_set_id = fields.Many2one(
        "federation.participant.set", readonly=True, copy=False
    )

    def action_open(self):
        self.write({"state": "open"})
        return True

    def action_close(self):
        self.write({"state": "closed"})
        return True

    def action_finalize(self):
        roles = self.env["federation.competition.role.assignment"]
        roles.assert_role(
            self.edition_id, "registration_manager", "competition_director"
        )
        for rec in self:
            if rec.state != "closed":
                raise ValidationError(
                    _("Close registration before finalizing participants.")
                )
            approved = rec.entry_ids.filtered(lambda x: x.state == "approved")
            if len(approved) < 2:
                raise ValidationError(_("At least two approved teams are required."))
            if len(approved.mapped("team_id")) != len(approved):
                raise ValidationError(_("The approved list contains duplicate teams."))
            rec._materialize_participant_set(approved)
        return True

    def _materialize_participant_set(self, approved_entries):
        """Create the immutable participant snapshot used by format planning.

        Registration entries and participant sets stay authoritative even when
        the streamlined team picker is used.  Keeping the materialization here
        lets the normal desk and the simplified workspace share the exact same
        legacy records, events and downstream contracts.
        """
        self.ensure_one()
        approved_entries = approved_entries.sorted(lambda entry: (entry.seed, entry.id))
        if len(approved_entries) < 2:
            raise ValidationError(_("At least two approved teams are required."))
        if len(approved_entries.mapped("team_id")) != len(approved_entries):
            raise ValidationError(_("The approved list contains duplicate teams."))
        pset = self.env["federation.participant.set"].create(
            {
                "name": _("Participants - %s") % self.division_id.display_name,
                "edition_id": self.edition_id.id,
                "division_id": self.division_id.id,
                "state": "finalized",
            }
        )
        self.env["federation.participant.set.line"].create(
            [
                {
                    "participant_set_id": pset.id,
                    "team_id": entry.team_id.id,
                    "seed": entry.seed,
                }
                for entry in approved_entries
            ]
        )
        self.write({"state": "finalized", "participant_set_id": pset.id})
        self.env["federation.competition.event"].emit(
            pset, "participant_set_finalized", {"team_count": len(approved_entries)}
        )
        return pset

    def materialize_direct_team_selection(self, teams):
        """Synchronize a direct selection into governed registration records.

        This command is intentionally conservative.  Repeating the same
        selection is idempotent.  A changed finalized selection is allowed only
        before a format version depends on it; otherwise operators must use the
        existing correction/versioning workflow.
        """
        self.ensure_one()
        self.env["federation.competition.role.assignment"].assert_role(
            self.edition_id, "registration_manager", "competition_director"
        )
        teams = self.env["federation.team"].browse(teams.ids).exists()
        if len(teams) < 2:
            raise ValidationError(_("Select at least two teams for the division."))
        for team in teams:
            error = self.division_id.get_team_eligibility_error(team)
            if not team.active:
                error = _("Only active teams can be selected.")
            if error:
                raise ValidationError(error)

        selected_ids = set(teams.ids)
        current = self.participant_set_id
        current_ids = set(current.line_ids.mapped("team_id").ids) if current else set()
        if current and current.state == "finalized" and current_ids == selected_ids:
            return current
        if current and current.state == "finalized":
            Structure = self.env.get("federation.competition.structure")
            dependent = (
                Structure.search_count([("participant_set_id", "=", current.id)])
                if Structure is not None
                else 0
            )
            if dependent:
                raise ValidationError(
                    _(
                        "This finalized team list already has a competition format. "
                        "Create a governed successor format instead of replacing its history."
                    )
                )
            current.write({"state": "superseded"})

        now = fields.Datetime.now()
        entries = self.entry_ids
        by_team = {entry.team_id.id: entry for entry in entries}
        approved = self.env["federation.competition.entry"]
        for seed, team in enumerate(teams.sorted(lambda item: (item.name or "", item.id)), 1):
            entry = by_team.get(team.id)
            values = {
                "seed": seed,
                "state": "approved",
                "submitted_by_id": self.env.user.id,
                "submitted_on": now,
                "reviewed_by_id": self.env.user.id,
                "reviewed_on": now,
                "review_note": _("Selected directly in the competition workspace."),
            }
            if entry:
                entry.write(values)
            else:
                entry = self.env["federation.competition.entry"].create(
                    {"window_id": self.id, "team_id": team.id, **values}
                )
            approved |= entry
        deselected = entries.filtered(
            lambda entry: entry.team_id.id not in selected_ids
            and entry.state != "withdrawn"
        )
        if deselected:
            deselected.write({"state": "withdrawn"})
        self.write({"state": "closed", "participant_set_id": False})
        participant_set = self._materialize_participant_set(approved)
        self.env["federation.competition.event"].emit(
            participant_set,
            "competition_teams_selected",
            {"team_count": len(teams), "source": "competition_workspace"},
        )
        return participant_set


class FederationCompetitionEntry(models.Model):
    _name = "federation.competition.entry"
    _description = "Competition Entry"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    window_id = fields.Many2one(
        "federation.registration.window", required=True, ondelete="cascade", index=True
    )
    edition_id = fields.Many2one(related="window_id.edition_id", store=True, index=True)
    team_id = fields.Many2one(
        "federation.team", required=True, ondelete="restrict", index=True
    )
    available_team_ids = fields.Many2many(
        "federation.team",
        compute="_compute_available_team_ids",
        string="Available Teams",
    )
    seed = fields.Integer()
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("withdrawn", "Withdrawn"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    review_note = fields.Text()
    submission_note = fields.Text()
    submitted_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    submitted_on = fields.Datetime(readonly=True, copy=False)
    reviewed_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    reviewed_on = fields.Datetime(readonly=True, copy=False)
    _unique_team = models.Constraint(
        "unique(window_id,team_id)", "A team can enter a registration window only once."
    )

    @api.depends(
        "window_id",
        "window_id.division_id",
        "window_id.division_id.category",
        "window_id.division_id.gender",
        "window_id.entry_ids.team_id",
    )
    def _compute_available_team_ids(self):
        """Compute teams eligible and not already entered in this window."""
        Team = self.env["federation.team"]
        eligible_teams_by_division = {}
        for division in self.mapped("window_id.division_id"):
            eligible_teams_by_division[division.id] = division.search_eligible_teams(
                extra_domain=[("active", "=", True)]
            )

        for rec in self:
            rec.available_team_ids = Team.browse([])
            if not rec.window_id or not rec.window_id.division_id:
                continue

            eligible_teams = eligible_teams_by_division.get(
                rec.window_id.division_id.id, Team.browse([])
            )
            registered_teams = (rec.window_id.entry_ids - rec).mapped("team_id")
            rec.available_team_ids = eligible_teams - registered_teams

    def _get_team_selection_error(self, team=None):
        """Return the reason a team cannot be used for this registration."""
        self.ensure_one()
        team = team or self.team_id
        if not team or not self.window_id or not self.window_id.division_id:
            return False

        duplicate = self.window_id.entry_ids.filtered(
            lambda entry: entry != self and entry.team_id == team
        )
        if duplicate:
            return _("Team '%(team)s' is already registered for this division.") % {
                "team": team.display_name
            }

        if not team.active:
            return _("Only active teams can be registered.")

        return self.window_id.division_id.get_team_eligibility_error(team)

    @api.onchange("window_id")
    def _onchange_window_id(self):
        """Limit team choices to eligible teams not already entered."""
        domain = [("id", "in", self.available_team_ids.ids)]
        if self.team_id and self.team_id not in self.available_team_ids:
            warning = {
                "title": _("Invalid Team"),
                "message": self._get_team_selection_error(),
            }
            self.team_id = False
            return {"domain": {"team_id": domain}, "warning": warning}
        return {"domain": {"team_id": domain}}

    @api.constrains("window_id", "team_id")
    def _check_team_selection(self):
        """Keep invalid team selections blocked server-side."""
        for rec in self:
            error = rec._get_team_selection_error()
            if error:
                raise ValidationError(error)

    def action_submit(self):
        invalid = self.filtered(
            lambda entry: entry.state not in ("draft", "rejected", "withdrawn")
        )
        if invalid:
            raise ValidationError(
                _("Only draft, returned, rejected, or withdrawn entries can be submitted.")
            )
        self.write(
            {
                "state": "submitted",
                "submitted_by_id": self.env.user.id,
                "submitted_on": fields.Datetime.now(),
                "reviewed_by_id": False,
                "reviewed_on": False,
            }
        )
        automatic = self.filtered(lambda entry: not entry.edition_id.registration_approval_required)
        if automatic:
            automatic.write(
                {
                    "state": "approved",
                    "reviewed_by_id": self.env.user.id,
                    "reviewed_on": fields.Datetime.now(),
                    "review_note": _("Automatically approved by competition workflow policy."),
                }
            )
        return True

    def action_approve(self):
        self.mapped("window_id.edition_id") and self.env[
            "federation.competition.role.assignment"
        ].assert_role(
            self[:1].edition_id, "registration_manager", "competition_director"
        )
        self.write(
            {
                "state": "approved",
                "reviewed_by_id": self.env.user.id,
                "reviewed_on": fields.Datetime.now(),
            }
        )
        return True

    def action_return(self, reason):
        if not reason or not reason.strip():
            raise ValidationError(_("A review reason is required."))
        self.write(
            {
                "state": "draft",
                "review_note": reason.strip(),
                "reviewed_by_id": self.env.user.id,
                "reviewed_on": fields.Datetime.now(),
            }
        )
        return True

    def action_reject(self, reason=False):
        self.write(
            {
                "state": "rejected",
                "review_note": reason.strip() if reason else self.review_note,
                "reviewed_by_id": self.env.user.id,
                "reviewed_on": fields.Datetime.now(),
            }
        )
        return True

    def action_withdraw(self):
        if self.filtered(lambda entry: entry.state == "approved"):
            raise ValidationError(_("Approved entries cannot be withdrawn directly."))
        if self.filtered(lambda entry: entry.state not in ("draft", "submitted", "rejected")):
            raise ValidationError(
                _("Only draft, submitted, or rejected entries can be withdrawn.")
            )
        self.write({"state": "withdrawn"})
        return True


class FederationParticipantSet(models.Model):
    _name = "federation.participant.set"
    _description = "Finalized Participant Set"
    _order = "id desc"
    name = fields.Char(required=True)
    edition_id = fields.Many2one(
        "federation.competition.edition", required=True, ondelete="cascade", index=True
    )
    division_id = fields.Many2one(
        "federation.tournament", required=True, ondelete="cascade", index=True
    )
    state = fields.Selection(
        [("draft", "Draft"), ("finalized", "Finalized"), ("superseded", "Superseded")],
        default="draft",
        required=True,
        index=True,
    )
    line_ids = fields.One2many(
        "federation.participant.set.line", "participant_set_id", readonly=True
    )


class FederationParticipantSetLine(models.Model):
    _name = "federation.participant.set.line"
    _description = "Participant Set Line"
    _order = "seed,id"
    participant_set_id = fields.Many2one(
        "federation.participant.set", required=True, ondelete="cascade", index=True
    )
    team_id = fields.Many2one(
        "federation.team", required=True, ondelete="restrict", index=True
    )
    seed = fields.Integer()
    _unique_team = models.Constraint(
        "unique(participant_set_id,team_id)",
        "A finalized participant set cannot contain duplicate teams.",
    )
