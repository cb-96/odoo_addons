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
        "representative_ids.is_current",
    )
    def _compute_portal_scope_ids(self):
        """Compute portal scope IDs."""
        for rec in self:
            current_reps = rec.representative_ids.filtered("is_current")
            rec.portal_club_scope_ids = current_reps.filtered(
                lambda rep: not rep.team_id
            ).mapped("club_id")
            rec.portal_team_scope_ids = current_reps.mapped("team_id")

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
