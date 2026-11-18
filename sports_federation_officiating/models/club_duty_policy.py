"""Versioned club-duty planning policies.

A policy states how club duties are planned for one season, or for every season
without its own policy: officials per match, playing-club avoidance and
fallback, preservation of existing coverage and the optimizer. Only drafts can
be edited. Activating a draft retires the active version of the same scope and
numbers the new one, so every reviewed plan names the exact policy version it
was planned under.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..duty_exact_solver import exact_available

COMMAND_CONTEXT = "club_duty_policy_command"
MANAGER_GROUP = "sports_federation_base.group_federation_manager"
PROTECTED_FIELDS = {
    "state",
    "version",
    "activated_by_id",
    "activated_on",
    "previous_id",
}
EDITABLE_AFTER_DRAFT = {"notes"}


class FederationClubDutyPolicy(models.Model):
    _name = "federation.club.duty.policy"
    _description = "Club-Duty Planning Policy"
    _order = "season_id, version desc, id desc"

    name = fields.Char(required=True)
    season_id = fields.Many2one(
        "federation.season",
        index=True,
        ondelete="restrict",
        help="Leave empty for the policy used by seasons without their own policy.",
    )
    version = fields.Integer(readonly=True, copy=False, default=0)
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("retired", "Retired")],
        default="draft",
        required=True,
        readonly=True,
        copy=False,
        index=True,
    )
    officials_per_match = fields.Integer(
        default=0, help="Zero uses each division rule set."
    )
    avoid_playing = fields.Boolean(
        string="Avoid clubs playing at the same time", default=True
    )
    allow_fallback = fields.Boolean(string="Allow playing-club fallback")
    preserve_existing = fields.Boolean(
        string="Preserve existing assignments", default=True
    )
    solver = fields.Selection(
        [
            ("local_search", "Built-in local search"),
            ("exact", "Exact optimizer (OR-Tools CP-SAT)"),
        ],
        string="Optimizer",
        default="local_search",
        required=True,
    )
    solver_effort = fields.Float(
        string="Optimizer effort",
        default=5.0,
        help="Deterministic CP-SAT work budget. The same inputs give the same "
        "plan on every server.",
    )
    exact_solver_available = fields.Boolean(
        compute="_compute_exact_solver_available"
    )
    previous_id = fields.Many2one(
        "federation.club.duty.policy",
        string="Previous version",
        readonly=True,
        copy=False,
        ondelete="set null",
    )
    activated_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    activated_on = fields.Datetime(readonly=True, copy=False)
    notes = fields.Text()

    def _compute_exact_solver_available(self):
        available = exact_available()
        for policy in self:
            policy.exact_solver_available = available

    @api.depends("name", "version", "state")
    def _compute_display_name(self):
        for policy in self:
            if policy.version:
                policy.display_name = "%s v%s" % (policy.name, policy.version)
            else:
                policy.display_name = _("%s (draft)") % policy.name

    @api.constrains("officials_per_match", "solver_effort")
    def _check_values(self):
        for policy in self:
            if not 0 <= policy.officials_per_match <= 5:
                raise ValidationError(
                    _("Officials per match must be between zero and five.")
                )
            if not 0 < policy.solver_effort <= 600:
                raise ValidationError(
                    _("Optimizer effort must be above zero and at most 600.")
                )

    @api.constrains("state", "season_id")
    def _check_single_active(self):
        for policy in self.filtered(lambda record: record.state == "active"):
            if self.search_count(
                [
                    ("state", "=", "active"),
                    ("season_id", "=", policy.season_id.id),
                    ("id", "!=", policy.id),
                ]
            ):
                raise ValidationError(
                    _("Only one club-duty policy version can be active per season.")
                )

    def _check_manager(self):
        if not self.env.user.has_group(MANAGER_GROUP):
            raise AccessError(
                _("Only federation managers may manage club-duty policies.")
            )

    @api.model_create_multi
    def create(self, values_list):
        if not self.env.context.get(COMMAND_CONTEXT):
            if any(PROTECTED_FIELDS & values.keys() for values in values_list):
                raise UserError(
                    _("Create a draft policy and use Activate to put it in force.")
                )
        return super().create(values_list)

    def write(self, values):
        if not self.env.context.get(COMMAND_CONTEXT):
            if PROTECTED_FIELDS & values.keys():
                raise UserError(
                    _("Use Activate or New version to change a policy's lifecycle.")
                )
            if set(values) - EDITABLE_AFTER_DRAFT and any(
                policy.state != "draft" for policy in self
            ):
                raise UserError(
                    _(
                        "Active and retired policy versions are read-only. "
                        "Create a new version to change the policy."
                    )
                )
        return super().write(values)

    def unlink(self):
        if any(policy.state != "draft" for policy in self):
            raise UserError(_("Only draft policy versions can be deleted."))
        return super().unlink()

    def action_activate(self):
        self._check_manager()
        for policy in self.sorted("id"):
            if policy.state != "draft":
                raise UserError(_("Only a draft policy version can be activated."))
            scope = [("season_id", "=", policy.season_id.id)]
            current = self.search(scope + [("state", "=", "active")])
            last = max(self.search(scope).mapped("version") or [0])
            command = {COMMAND_CONTEXT: True}
            current.with_context(**command).write({"state": "retired"})
            policy.with_context(**command).write(
                {
                    "state": "active",
                    "version": last + 1,
                    "activated_by_id": self.env.user.id,
                    "activated_on": fields.Datetime.now(),
                    "previous_id": policy.previous_id.id or current[:1].id,
                }
            )
        return True

    def action_new_version(self):
        self.ensure_one()
        self._check_manager()
        if self.state == "draft":
            raise UserError(_("This version is still a draft; edit it directly."))
        draft = self.with_context(**{COMMAND_CONTEXT: True}).copy(
            {"previous_id": self.id}
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": draft.id,
            "view_mode": "form",
            "target": "current",
        }

    def review_options(self):
        """Options for the club-duty review and governed club-duty runs."""
        self.ensure_one()
        return {
            "officials_per_match": self.officials_per_match,
            "avoid_playing": self.avoid_playing,
            "allow_fallback": self.allow_fallback,
            "preserve_existing": self.preserve_existing,
        }

    @api.model
    def _active_for_season(self, season):
        """Active policy of ``season``, else the active default policy."""
        active = [("state", "=", "active")]
        policy = self.browse()
        if season:
            policy = self.search(active + [("season_id", "=", season.id)], limit=1)
        return policy or self.search(active + [("season_id", "=", False)], limit=1)
