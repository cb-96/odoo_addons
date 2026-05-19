from odoo import api, fields, models


class FederationClub(models.Model):
    """Extend federation.club with club roles integration."""

    _inherit = "federation.club"

    representative_ids = fields.One2many(
        "federation.club.representative",
        "club_id",
        string="Club Representatives",
    )
    representative_count = fields.Integer(
        string="Representative Count",
        compute="_compute_representative_count",
        store=True,
    )

    # Smart button helper fields for filtered counts
    primary_contact_count = fields.Integer(
        string="Primary Contacts",
        compute="_compute_contact_counts",
        store=True,
    )
    competition_contact_count = fields.Integer(
        string="Competition Contacts",
        compute="_compute_contact_counts",
        store=True,
    )
    finance_contact_count = fields.Integer(
        string="Finance Contacts",
        compute="_compute_contact_counts",
        store=True,
    )
    safeguarding_contact_count = fields.Integer(
        string="Safeguarding Contacts",
        compute="_compute_contact_counts",
        store=True,
    )

    @api.depends("representative_ids")
    def _compute_representative_count(self):
        """Compute representative count."""
        for rec in self:
            rec.representative_count = len(rec.representative_ids)

    @api.depends(
        "representative_ids",
        "representative_ids.is_primary",
        "representative_ids.role_type_id.is_competition_contact",
        "representative_ids.role_type_id.is_finance_contact",
        "representative_ids.role_type_id.is_safeguarding_contact",
    )
    def _compute_contact_counts(self):
        """Compute contact counts."""
        for rec in self:
            reps = rec.representative_ids
            rec.primary_contact_count = len(reps.filtered("is_primary"))
            rec.competition_contact_count = len(
                reps.filtered(lambda r: r.role_type_id.is_competition_contact)
            )
            rec.finance_contact_count = len(
                reps.filtered(lambda r: r.role_type_id.is_finance_contact)
            )
            rec.safeguarding_contact_count = len(
                reps.filtered(lambda r: r.role_type_id.is_safeguarding_contact)
            )

    def action_view_representatives(self):
        """Open the representatives list for this club."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Club Representatives",
            "res_model": "federation.club.representative",
            "view_mode": "tree,form",
            "domain": [("club_id", "=", self.id)],
            "context": {"default_club_id": self.id},
        }

    def action_view_primary_contacts(self):
        """Open the primary contacts list for this club."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Primary Contacts",
            "res_model": "federation.club.representative",
            "view_mode": "tree,form",
            "domain": [("club_id", "=", self.id), ("is_primary", "=", True)],
            "context": {"default_club_id": self.id},
        }

    def action_view_competition_contacts(self):
        """Open the competition contacts list for this club."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Competition Contacts",
            "res_model": "federation.club.representative",
            "view_mode": "tree,form",
            "domain": [
                ("club_id", "=", self.id),
                ("role_type_id.is_competition_contact", "=", True),
            ],
            "context": {"default_club_id": self.id},
        }

    def action_view_finance_contacts(self):
        """Open the finance contacts list for this club."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Finance Contacts",
            "res_model": "federation.club.representative",
            "view_mode": "tree,form",
            "domain": [
                ("club_id", "=", self.id),
                ("role_type_id.is_finance_contact", "=", True),
            ],
            "context": {"default_club_id": self.id},
        }

    def action_view_safeguarding_contacts(self):
        """Open the safeguarding contacts list for this club."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Safeguarding Contacts",
            "res_model": "federation.club.representative",
            "view_mode": "tree,form",
            "domain": [
                ("club_id", "=", self.id),
                ("role_type_id.is_safeguarding_contact", "=", True),
            ],
            "context": {"default_club_id": self.id},
        }
