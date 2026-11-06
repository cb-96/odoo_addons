from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ROLE_SELECTION = [
    ("administrator", "Competition Administrator"),
    ("registration_manager", "Registration Manager"),
    ("competition_designer", "Competition Designer"),
    ("calendar_planner", "Calendar Planner"),
    ("schedule_planner", "Schedule Planner"),
    ("schedule_approver", "Schedule Approver"),
    ("matchday_manager", "Match-Day Manager"),
    ("results_officer", "Results Officer"),
    ("competition_director", "Competition Director"),
]


class FederationCompetitionEdition(models.Model):
    _inherit = "federation.competition.edition"
    role_assignment_ids = fields.One2many(
        "federation.competition.role.assignment", "edition_id"
    )
    event_ids = fields.One2many(
        "federation.competition.event", "edition_id", readonly=True
    )

    def transition_competition_state(self, target, reason=False):
        """Move the edition through its canonical lifecycle and emit an event."""
        allowed = {
            "draft": {"open", "cancelled"},
            "open": {"in_progress", "cancelled"},
            "in_progress": {"closed", "cancelled"},
            "closed": set(),
            "cancelled": {"draft"},
        }
        for rec in self:
            if target == rec.state:
                continue
            if target == "closed":
                blockers = rec._get_close_blockers()
                if blockers:
                    raise ValidationError(
                        _("%(edition)s cannot be closed yet:\n- %(blockers)s")
                        % {"edition": rec.display_name, "blockers": "\n- ".join(blockers)}
                    )
            if rec.state == "cancelled" and target == "draft":
                blockers = rec._get_reset_blockers()
                if blockers:
                    raise ValidationError("\n".join(blockers))
            if target not in allowed.get(rec.state, set()):
                raise ValidationError(
                    _(
                        "Invalid competition transition from %(source)s to %(target)s.",
                        source=rec.state,
                        target=target,
                    )
                )
            old = rec.state
            rec.state = target
            self.env["federation.competition.event"].emit(
                rec,
                "competition_state_changed",
                {"from": old, "to": target, "reason": reason or ""},
            )
        return True

    def _get_close_blockers(self):
        """Reasons the competition cannot be closed. Extended by later modules."""
        self.ensure_one()
        return []

    def _get_reset_blockers(self):
        """A cancelled competition with official results stays cancelled."""
        self.ensure_one()
        Match = self.env["federation.match"]
        if "result_state" in Match._fields and Match.search_count(
            [("tournament_id", "in", self.tournament_ids.ids), ("result_state", "=", "approved")],
            limit=1,
        ):
            return [_("Approved results exist; create a new competition instead.")]
        return []

    def _advance_lifecycle(self, target, reason=False):
        """Move forward to ``target`` (open or in_progress) as work happens.

        Called after an already authorized action (schedule publication, a
        gameday opening). Closed and cancelled competitions are left alone.
        """
        order = ["draft", "open", "in_progress"]
        for rec in self.sudo():
            if rec.state not in order or order.index(rec.state) >= order.index(target):
                continue
            for step in order[order.index(rec.state) + 1 : order.index(target) + 1]:
                rec.transition_competition_state(step, reason=reason)
        return True

    # Form buttons use the same guarded transitions as the automatic steps.
    def action_open(self):
        return self.transition_competition_state("open")

    def action_start(self):
        return self.transition_competition_state("in_progress")

    def action_close(self):
        return self.transition_competition_state("closed")

    def action_cancel(self):
        return self.transition_competition_state("cancelled")

    def action_draft(self):
        return self.transition_competition_state("draft")


class FederationCompetitionRoleAssignment(models.Model):
    _name = "federation.competition.role.assignment"
    _description = "Competition Role Assignment"
    _order = "edition_id, role, user_id"
    edition_id = fields.Many2one(
        "federation.competition.edition", required=True, ondelete="cascade", index=True
    )
    role = fields.Selection(ROLE_SELECTION, required=True, index=True)
    user_id = fields.Many2one(
        "res.users", required=True, ondelete="cascade", index=True
    )
    active = fields.Boolean(default=True)
    _unique_role_user = models.Constraint(
        "unique(edition_id, role, user_id)",
        "A user can hold a competition role only once.",
    )

    @api.model
    def assert_role(self, edition, *roles):
        if self.env.user.has_group("sports_federation_base.group_federation_manager"):
            return True
        # Role assignments are administrator-managed records.  The authorization
        # guard must be able to inspect them without granting every operational
        # role broad read access to the assignment model.
        if not self.sudo().search_count(
            [
                ("edition_id", "=", edition.id),
                ("user_id", "=", self.env.user.id),
                ("role", "in", list(roles)),
                ("active", "=", True),
            ]
        ):
            role_labels = dict(ROLE_SELECTION)
            required = ", ".join(role_labels.get(role, role) for role in roles)
            raise ValidationError(
                _(
                    "This action requires one of these competition roles: %(roles)s. "
                    "Ask the Competition Administrator to assign the role, or hand "
                    "this item to a user who already has it.",
                    roles=required,
                )
            )
        return True
