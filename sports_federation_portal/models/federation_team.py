from odoo import _, api, models
from odoo.exceptions import AccessError, ValidationError


class FederationTeam(models.Model):
    _inherit = "federation.team"

    @api.model
    def _portal_create_team(self, club, values=None, user=None):
        """Create a club-owned team through the portal service boundary."""
        user = user or self.env.user
        PortalPrivilege = self.env["federation.portal.privilege"]
        values = values or {}
        club = PortalPrivilege.elevate(club, user=user)
        if not club.exists():
            raise ValidationError(_("Select a valid club before creating a team."))

        represented_clubs = PortalPrivilege.elevate(
            self.env["federation.club.representative"],
            user=user,
        )._get_clubs_for_user(user=user)
        if club not in represented_clubs:
            raise AccessError(_("You can only create teams for your own club."))

        name = (values.get("name") or "").strip()
        category = (values.get("category") or "").strip()
        gender = (values.get("gender") or "").strip()
        if not name:
            raise ValidationError(_("Team name is required."))
        if category not in dict(self._fields["category"].selection):
            raise ValidationError(_("Choose a valid team category."))
        if gender not in dict(self._fields["gender"].selection):
            raise ValidationError(_("Choose a valid team gender."))

        return PortalPrivilege.portal_create(
            self,
            {
                "name": name,
                "club_id": club.id,
                "category": category,
                "gender": gender,
                "email": (values.get("email") or "").strip() or False,
                "phone": (values.get("phone") or "").strip() or False,
            },
            user=user,
        )
