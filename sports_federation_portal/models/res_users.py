from odoo import api, fields, models


class ResUsers(models.Model):
    """Extend res.users with club representative links for portal ownership."""

    _inherit = "res.users"

    representative_ids = fields.One2many(
        "federation.club.representative",
        "user_id",
        string="Portal Representative Roles",
        help="Club representative records linked to this user for portal access.",
    )
    representative_count = fields.Integer(
        string="Portal Representative Role Count",
        compute="_compute_representative_count",
        store=True,
    )
    represented_club_ids = fields.Many2many(
        "federation.club",
        relation="federation_user_represented_club_rel",
        column1="user_id",
        column2="club_id",
        string="Portal Represented Clubs",
        compute="_compute_represented_club_ids",
        store=True,
        help="Clubs this user represents (via representative records).",
    )
    portal_club_scope_ids = fields.Many2many(
        "federation.club",
        relation="federation_user_portal_club_scope_rel",
        column1="user_id",
        column2="club_id",
        string="Portal Club Scope",
        compute="_compute_portal_scope_ids",
        store=True,
        help="Whole-club portal scope derived from representative roles without team restrictions.",
    )
    portal_team_scope_ids = fields.Many2many(
        "federation.team",
        relation="federation_user_portal_team_scope_rel",
        column1="user_id",
        column2="team_id",
        string="Portal Team Scope",
        compute="_compute_portal_scope_ids",
        store=True,
        help="Team-scoped portal access derived from coach or manager representative roles.",
    )

    @api.depends("representative_ids")
    def _compute_representative_count(self):
        """Compute representative count."""
        for rec in self:
            rec.representative_count = len(rec.representative_ids)

    @api.depends("representative_ids.club_id")
    def _compute_represented_club_ids(self):
        """Compute represented club IDs."""
        for rec in self:
            rec.represented_club_ids = rec.representative_ids.mapped("club_id")

    @api.depends(
        "representative_ids.club_id",
        "representative_ids.team_id",
        "representative_ids.active",
        "representative_ids.date_start",
        "representative_ids.date_end",
    )
    def _compute_portal_scope_ids(self):
        """Compute portal scope IDs."""
        today = fields.Date.context_today(self)
        for rec in self:
            clubs, teams = rec._portal_scopes_on(today)
            rec.portal_club_scope_ids = clubs
            rec.portal_team_scope_ids = teams

    def _portal_scopes_on(self, today):
        """(whole-club scope, team scope) from the tenures valid on ``today``."""
        self.ensure_one()
        current = self.representative_ids.filtered(
            lambda rep: rep._is_current_on(today)
        )
        return (
            current.filtered(lambda rep: not rep.team_id).mapped("club_id"),
            current.mapped("team_id"),
        )

    @api.model
    def _refresh_portal_scopes(self):
        """Recompute the stored portal scopes that changed only because time passed.

        Record rules read ``portal_club_scope_ids``/``portal_team_scope_ids``.
        They are stored, so a tenure that ended (or started) by date must be
        recomputed here; no edit triggers it.
        """
        today = fields.Date.context_today(self)
        timed = (
            self.env["federation.club.representative"]
            .sudo()
            .with_context(active_test=False)
            .search(["|", ("date_start", "!=", False), ("date_end", "!=", False)])
        )
        stale = self.browse()
        for user in timed.mapped("user_id").sudo():
            clubs, teams = user._portal_scopes_on(today)
            if (
                clubs != user.portal_club_scope_ids
                or teams != user.portal_team_scope_ids
            ):
                stale |= user
        if stale:
            for name in ("portal_club_scope_ids", "portal_team_scope_ids"):
                self.env.add_to_compute(self._fields[name], stale)
            # Compute now, for today's date, instead of leaving it to whatever
            # flushes the transaction later.
            stale.mapped("portal_club_scope_ids")
            stale.mapped("portal_team_scope_ids")
            stale.flush_recordset(
                ["portal_club_scope_ids", "portal_team_scope_ids"]
            )
            # Record rules read these fields, and Odoo caches the domain it
            # evaluates for each user. Without this the old scope keeps
            # applying until the cache is cleared by something else.
            self.env.registry.clear_cache()
        return stale

    def action_view_federation_representatives(self):
        """Open the representative roles list for this user."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Club Representative Roles",
            "res_model": "federation.club.representative",
            "view_mode": "tree,form",
            "domain": [("user_id", "=", self.id)],
            "context": {"default_user_id": self.id},
        }
