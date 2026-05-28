from odoo import _, api, models
from odoo.exceptions import AccessError, ValidationError


class FederationPlayerPortal(models.Model):
    _inherit = "federation.player"

    @api.model
    def _portal_create_player(self, club, values=None, user=None):
        """Create a player and register them with a club through the portal service boundary.

        Args:
            club: federation.club record that the player should belong to.
            values: dict with player field values (first_name, last_name required).
            user: res.users record; defaults to env.user.

        Returns:
            The created federation.player record.
        """
        user = user or self.env.user
        PortalPrivilege = self.env["federation.portal.privilege"]
        values = values or {}

        club = PortalPrivilege.elevate(club, user=user)
        if not club.exists():
            raise ValidationError(_("Select a valid club before adding a player."))

        represented_clubs = PortalPrivilege.elevate(
            self.env["federation.club.representative"],
            user=user,
        )._get_clubs_for_user(user=user)
        if club not in represented_clubs:
            raise AccessError(_("You can only add players to your own club."))

        first_name = (values.get("first_name") or "").strip()
        last_name = (values.get("last_name") or "").strip()
        if not first_name:
            raise ValidationError(_("First name is required."))
        if not last_name:
            raise ValidationError(_("Last name is required."))

        player_vals = {
            "first_name": first_name,
            "last_name": last_name,
            "club_id": club.id,
        }

        birth_date = (values.get("birth_date") or "").strip() or False
        if birth_date:
            player_vals["birth_date"] = birth_date

        gender = (values.get("gender") or "").strip()
        valid_genders = dict(self._fields["gender"].selection)
        if gender and gender in valid_genders:
            player_vals["gender"] = gender

        email = (values.get("email") or "").strip() or False
        if email:
            player_vals["email"] = email

        phone = (values.get("phone") or "").strip() or False
        if phone:
            player_vals["phone"] = phone

        player = PortalPrivilege.portal_create(self, player_vals, user=user)

        self._portal_create_player_finance_event(player, club)

        return player

    @api.model
    def _portal_create_player_finance_event(self, player, club):
        """Create an optional member registration finance event.

        Guarded by env.get() so the feature only activates when
        sports_federation_finance_bridge is installed.
        """
        FinanceEvent = self.env.get("federation.finance.event")
        if FinanceEvent is None:
            return
        FeeType = self.env.get("federation.fee.type")
        if FeeType is None:
            return
        fee_type = FeeType.sudo().search(
            [("code", "=", "member_registration"), ("active", "=", True)], limit=1
        )
        if not fee_type:
            return
        FinanceEvent.sudo().create_from_source(
            player,
            fee_type,
            event_type="charge",
            note=_("Member registration fee for %(player)s at %(club)s")
            % {"player": player.name, "club": club.name},
        )
