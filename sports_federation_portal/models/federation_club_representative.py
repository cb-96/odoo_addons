from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class FederationClubRepresentative(models.Model):
    """Club representative with role-based contact management and portal access.

    Manages club contacts with configurable role types, tenure dates, primary
    contact flags, and portal ownership anchoring for secure club access.
    """

    _name = "federation.club.representative"
    _description = "Club Representative"
    _rec_name = "display_name"
    _order = "club_id, is_primary desc, role_type_id, partner_id"

    # Core relationships
    club_id = fields.Many2one(
        "federation.club",
        string="Club",
        required=True,
        ondelete="cascade",
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        required=True,
        ondelete="cascade",
        index=True,
        help="The partner record representing this person.",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Linked User",
        ondelete="set null",
        help="Optional linked portal user. This is the primary portal ownership anchor.",
    )

    # Role configuration
    role_type_id = fields.Many2one(
        "federation.club.role.type",
        string="Role Type",
        required=True,
        ondelete="restrict",
        index=True,
    )
    team_id = fields.Many2one(
        "federation.team",
        string="Assigned Team",
        ondelete="set null",
        index=True,
        domain="[('club_id', '=', club_id)]",
        help="Optional team scope for coach or manager roles.",
    )
    is_primary = fields.Boolean(
        string="Primary Contact",
        default=False,
        help="If checked, this representative is the primary contact for this role type.",
    )
    operational_role = fields.Selection(
        [
            ("competition_contact", "Competition contact"),
            ("team_admin", "Team administrator"),
            ("roster_manager", "Roster manager"),
            ("officials_coordinator", "Officials coordinator"),
            ("result_reviewer", "Result reviewer"),
            ("backup", "Backup representative"),
        ],
        string="Operational Responsibility",
        index=True,
    )
    delegated_to_id = fields.Many2one(
        "federation.club.representative",
        string="Temporary Delegate",
        domain="[('club_id', '=', club_id), ('is_current', '=', True)]",
        ondelete="set null",
    )
    delegation_until = fields.Date(string="Delegation Until")
    effective_user_id = fields.Many2one(
        "res.users", compute="_compute_effective_user", store=True
    )

    role = fields.Selection(
        [
            ("primary", "Primary Representative"),
            ("secondary", "Secondary Representative"),
        ],
        string="Portal Role",
        default="primary",
    )

    # Temporal fields
    date_start = fields.Date(
        string="Start Date",
        help="Date when this representative assumed the role.",
    )
    date_end = fields.Date(
        string="End Date",
        help="Date when this representative's role ended.",
    )

    # Status and metadata
    active = fields.Boolean(default=True)
    notes = fields.Text(string="Notes")

    # Computed fields
    display_name = fields.Char(
        compute="_compute_display_name",
        store=True,
    )
    # Not stored: a tenure ends by date, not by an edit, so a stored flag would
    # keep granting access after ``date_end``. Searches on this field are
    # translated to the exact date conditions (see ``_search_is_current``).
    is_current = fields.Boolean(
        string="Currently Active",
        compute="_compute_is_current",
        search="_search_is_current",
        help="True if the representative's tenure is currently active.",
    )

    @api.depends("partner_id", "club_id", "team_id", "role_type_id", "is_primary")
    def _compute_display_name(self):
        """Compute display name."""
        for rec in self:
            parts = []
            if rec.partner_id:
                parts.append(rec.partner_id.name)
            if rec.club_id:
                parts.append(rec.club_id.name)
            if rec.team_id:
                parts.append(rec.team_id.name)
            if rec.role_type_id:
                parts.append(rec.role_type_id.name)
            if rec.is_primary:
                parts.append("(Primary)")
            rec.display_name = " - ".join(parts) if parts else "New"

    @api.depends(
        "user_id",
        "delegated_to_id.user_id",
        "delegated_to_id.is_current",
        "delegation_until",
        "active",
    )
    def _compute_effective_user(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.effective_user_id = rec._effective_user_on(today)

    def _effective_user_on(self, today):
        """The user acting for this representative on ``today``."""
        self.ensure_one()
        delegate_active = (
            self.delegated_to_id
            and self.delegated_to_id._is_current_on(today)
            and (not self.delegation_until or self.delegation_until >= today)
        )
        return self.delegated_to_id.user_id if delegate_active else self.user_id

    @api.constrains("delegated_to_id", "delegation_until")
    def _check_delegation_scope(self):
        for rec in self:
            if rec.delegated_to_id and rec.delegated_to_id.club_id != rec.club_id:
                raise ValidationError(_("Delegation must stay within the same club."))

    def _is_current_on(self, today):
        """Whether the tenure covers ``today`` (empty dates are open-ended)."""
        self.ensure_one()
        if not self.active:
            return False
        if self.date_start and self.date_start > today:
            return False
        if self.date_end and self.date_end < today:
            return False
        return True

    @api.depends("date_start", "date_end", "active")
    def _compute_is_current(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_current = rec._is_current_on(today)

    @api.model
    def _search_is_current(self, operator, value):
        """Exact date conditions, so the answer never depends on a stored flag."""
        if operator in ("=", "!="):
            values = {bool(value)}
        elif operator in ("in", "not in"):
            values = {bool(item) for item in value}
        else:
            raise UserError(
                _("Unsupported operator %s for Currently Active.", operator)
            )
        if operator in ("!=", "not in"):
            values = {True, False} - values
        if values == {True, False}:
            return [(1, "=", 1)]
        if not values:
            return [(0, "=", 1)]
        today = fields.Date.context_today(self)
        if True in values:
            return [
                ("active", "=", True),
                "|",
                ("date_start", "=", False),
                ("date_start", "<=", today),
                "|",
                ("date_end", "=", False),
                ("date_end", ">=", today),
            ]
        return [
            "|",
            "|",
            ("active", "=", False),
            ("date_start", ">", today),
            ("date_end", "<", today),
        ]

    @api.model
    def _cron_refresh_time_based_state(self):
        """Bring stored values that depend on today's date up to date.

        A tenure or a delegation ends by date, not by an edit, so nothing
        recomputes the stored portal scopes of the user or the effective user
        of a delegation when the date passes. This job does, every hour, so an
        ended tenure loses its portal access within the hour after UTC midnight.
        """
        today = fields.Date.context_today(self)
        self.env["res.users"].sudo()._refresh_portal_scopes()
        delegations = (
            self.sudo()
            .with_context(active_test=False)
            .search([("delegated_to_id", "!=", False)])
        )
        stale = delegations.filtered(
            lambda rep: rep.effective_user_id != rep._effective_user_on(today)
        )
        if stale:
            self.env.add_to_compute(self._fields["effective_user_id"], stale)
            # Compute now, for today's date, before anything else flushes.
            stale.mapped("effective_user_id")
        self.env.flush_all()
        return True

    @api.constrains("date_start", "date_end")
    def _check_dates(self):
        """Validate dates."""
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_start > rec.date_end:
                raise ValidationError("Start date cannot be after end date.")

    @api.constrains("club_id", "team_id", "role_type_id")
    def _check_team_scope(self):
        """Validate team scope."""
        for rec in self:
            if rec.team_id and rec.team_id.club_id != rec.club_id:
                raise ValidationError(
                    "Assigned team must belong to the same club as the representative record."
                )
            if rec.role_type_id.team_scoped and not rec.team_id:
                raise ValidationError(
                    "Team-scoped role types require an assigned team."
                )
            if rec.team_id and rec.role_type_id and not rec.role_type_id.team_scoped:
                raise ValidationError(
                    "Only team-scoped role types can be assigned to a specific team."
                )

    @api.constrains("partner_id", "club_id", "role_type_id", "team_id")
    def _check_partner_scope_uniqueness(self):
        """Validate partner scope uniqueness."""
        for rec in self:
            domain = [
                ("id", "!=", rec.id),
                ("partner_id", "=", rec.partner_id.id),
                ("club_id", "=", rec.club_id.id),
                ("role_type_id", "=", rec.role_type_id.id),
            ]
            if rec.team_id:
                domain.append(("team_id", "=", rec.team_id.id))
            else:
                domain.append(("team_id", "=", False))
            duplicate = self.with_context(active_test=False).search(domain, limit=1)
            if duplicate:
                raise ValidationError(
                    "A partner can only have one representative record per club, role type, and team scope."
                )

    @api.constrains("user_id", "club_id", "role_type_id", "team_id")
    def _check_user_scope_uniqueness(self):
        """Validate user scope uniqueness."""
        for rec in self.filtered("user_id"):
            domain = [
                ("id", "!=", rec.id),
                ("user_id", "=", rec.user_id.id),
                ("club_id", "=", rec.club_id.id),
                ("role_type_id", "=", rec.role_type_id.id),
            ]
            if rec.team_id:
                domain.append(("team_id", "=", rec.team_id.id))
            else:
                domain.append(("team_id", "=", False))
            duplicate = self.with_context(active_test=False).search(domain, limit=1)
            if duplicate:
                raise ValidationError(
                    "A user can only have one representative record per club, role type, and team scope."
                )

    @api.constrains("is_primary", "club_id", "role_type_id")
    def _check_primary_uniqueness(self):
        """Ensure only one primary representative per club and role type."""
        for rec in self:
            if rec.is_primary:
                domain = [
                    ("club_id", "=", rec.club_id.id),
                    ("role_type_id", "=", rec.role_type_id.id),
                    ("is_primary", "=", True),
                    ("id", "!=", rec.id),
                ]
                existing = self.search(domain, limit=1)
                if existing:
                    raise ValidationError(
                        f"There is already a primary representative for "
                        f"'{rec.role_type_id.name}' at club '{rec.club_id.name}'."
                    )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_representative_user_access_mode()
        return records

    def write(self, vals):
        result = super().write(vals)
        if {"user_id", "active", "date_start", "date_end"}.intersection(vals):
            self._check_representative_user_access_mode()
        return result

    def _check_representative_user_access_mode(self):
        """Keep representatives portal-only unless they hold a federation function."""
        internal_group = self.env.ref("base.group_user")
        federation_group = self.env.ref("sports_federation_base.group_federation_user")
        portal_group = self.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        for user in self.filtered(lambda record: record.is_current).mapped("user_id"):
            if (
                internal_group in user.group_ids
                and federation_group not in user.group_ids
            ):
                raise ValidationError(
                    _(
                        "A club representative without a federation function must use "
                        "portal access and cannot be an internal Odoo user."
                    )
                )
            if (
                federation_group not in user.group_ids
                and portal_group not in user.group_ids
            ):
                user.sudo().write({"group_ids": [(4, portal_group.id)]})

    @api.onchange("user_id")
    def _onchange_user_id_portal(self):
        """Auto-populate partner_id from the linked user when set."""
        if self.user_id and not self.partner_id:
            self.partner_id = self.user_id.partner_id

    def action_view_partner(self):
        """Execute the view partner action."""
        self.ensure_one()
        return {
            "name": _("Contact"),
            "type": "ir.actions.act_window",
            "res_model": "res.partner",
            "res_id": self.partner_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_user(self):
        """Execute the view user action."""
        self.ensure_one()
        return {
            "name": _("User"),
            "type": "ir.actions.act_window",
            "res_model": "res.users",
            "res_id": self.user_id.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def _get_club_for_user(self, user=None):
        """Return the first active club for the given user (or current user)."""
        user = user or self.env.user
        rep = self.sudo().search(
            [
                ("user_id", "=", user.id),
                ("is_current", "=", True),
            ],
            limit=1,
        )
        return rep.club_id if rep else self.env["federation.club"]

    @api.model
    def _get_clubs_for_user(self, user=None):
        """Return all active clubs the given user represents."""
        user = user or self.env.user
        reps = self.sudo().search(
            [
                ("user_id", "=", user.id),
                ("is_current", "=", True),
            ]
        )
        return reps.mapped("club_id")

    @api.model
    def _get_club_scope_for_user(self, user=None):
        """Return clubs for whole-club portal roles only."""
        user = user or self.env.user
        reps = self.sudo().search(
            [
                ("user_id", "=", user.id),
                ("is_current", "=", True),
                ("team_id", "=", False),
            ]
        )
        return reps.mapped("club_id")

    @api.model
    def _get_teams_for_user(self, user=None):
        """Return teams explicitly assigned to the given user's portal roles."""
        user = user or self.env.user
        reps = self.sudo().search(
            [
                ("user_id", "=", user.id),
                ("is_current", "=", True),
                ("team_id", "!=", False),
            ]
        )
        return reps.mapped("team_id")

    @api.model
    def _get_primary_contact(self, club, role_type_code=None):
        """Return the primary contact for a club and optional role type code."""
        domain = [
            ("club_id", "=", club.id),
            ("is_primary", "=", True),
            ("is_current", "=", True),
        ]
        if role_type_code:
            role_type = self.env["federation.club.role.type"].get_by_code(
                role_type_code
            )
            if role_type:
                domain.append(("role_type_id", "=", role_type.id))
        return self.search(domain, limit=1)

    @api.model
    def _get_portal_ownership_domain(self, user=None):
        """Return domain for records owned by the given user via representative link."""
        user = user or self.env.user
        return [("id", "in", user.representative_ids.mapped("club_id").ids)]
