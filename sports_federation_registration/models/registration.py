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
            pset = self.env["federation.participant.set"].create(
                {
                    "name": _("Participants - %s") % rec.division_id.display_name,
                    "edition_id": rec.edition_id.id,
                    "division_id": rec.division_id.id,
                    "state": "finalized",
                }
            )
            self.env["federation.participant.set.line"].create(
                [
                    {
                        "participant_set_id": pset.id,
                        "team_id": e.team_id.id,
                        "seed": e.seed,
                    }
                    for e in approved
                ]
            )
            rec.write({"state": "finalized", "participant_set_id": pset.id})
            self.env["federation.competition.event"].emit(
                pset, "participant_set_finalized", {"team_count": len(approved)}
            )
        return True


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
        invalid = self.filtered(lambda entry: entry.state not in ("draft", "rejected"))
        if invalid:
            raise ValidationError(_("Only draft or rejected entries can be submitted."))
        self.write(
            {
                "state": "submitted",
                "submitted_by_id": self.env.user.id,
                "submitted_on": fields.Datetime.now(),
                "reviewed_by_id": False,
                "reviewed_on": False,
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
