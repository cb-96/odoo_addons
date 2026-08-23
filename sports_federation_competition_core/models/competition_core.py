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
    engine_state = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("finished", "Finished"),
            ("cancelled", "Cancelled"),
            ("archived", "Archived"),
        ],
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )
    role_assignment_ids = fields.One2many(
        "federation.competition.role.assignment", "edition_id"
    )
    event_ids = fields.One2many(
        "federation.competition.event", "edition_id", readonly=True
    )

    def transition_engine_state(self, target, reason=False):
        allowed = {
            "draft": {"active", "cancelled"},
            "active": {"finished", "cancelled"},
            "finished": {"archived"},
            "cancelled": {"archived"},
            "archived": set(),
        }
        for rec in self:
            if target == rec.engine_state:
                continue
            if target not in allowed.get(rec.engine_state, set()):
                raise ValidationError(
                    _(
                        "Invalid competition transition from %(source)s to %(target)s.",
                        source=rec.engine_state,
                        target=target,
                    )
                )
            old = rec.engine_state
            rec.engine_state = target
            self.env["federation.competition.event"].emit(
                rec,
                "competition_state_changed",
                {"from": old, "to": target, "reason": reason or False},
            )
        return True


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
            raise ValidationError(
                _("You are not assigned to the required competition role.")
            )
        return True
