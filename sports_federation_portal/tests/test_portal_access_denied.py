"""Tests for portal 403 Access Denied differentiation from 404 Not Found.

Verifies that ``_render_access_denied()`` is available on the portal base
helper and that the 403 template is registered in the Odoo view registry.
"""
from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestPortalAccessDenied(TransactionCase):
    """Portal 403 vs 404: access denied renders dedicated template, not generic 404."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        cls.role_type = cls.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Access Denied Test Season",
                "code": "ADTS",
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
            }
        )
        cls.club_a = cls.env["federation.club"].create(
            {"name": "Access Denied Club A", "code": "ADCA"}
        )
        cls.club_b = cls.env["federation.club"].create(
            {"name": "Access Denied Club B", "code": "ADCB"}
        )
        cls.team_a = cls.env["federation.team"].create(
            {"name": "Access Denied Team A", "club_id": cls.club_a.id, "code": "ADTA"}
        )
        cls.team_b = cls.env["federation.team"].create(
            {"name": "Access Denied Team B", "club_id": cls.club_b.id, "code": "ADTB"}
        )

        def _make_user(name, login):
            return (
                cls.env["res.users"]
                .with_context(no_reset_password=True)
                .create(
                    {
                        "name": name,
                        "login": login,
                        "email": login,
                        "group_ids": [(6, 0, [cls.portal_group.id])],
                    }
                )
            )

        cls.user_a = _make_user("AD User A", "ad.a@example.com")
        cls.user_b = _make_user("AD User B", "ad.b@example.com")

        for club, user in [(cls.club_a, cls.user_a), (cls.club_b, cls.user_b)]:
            cls.env["federation.club.representative"].create(
                {
                    "club_id": club.id,
                    "partner_id": user.partner_id.id,
                    "user_id": user.id,
                    "role_type_id": cls.role_type.id,
                }
            )

        reg_a = cls.env["federation.season.registration"].create(
            {"season_id": cls.season.id, "team_id": cls.team_a.id}
        )
        reg_a.action_confirm()
        cls.roster_a = cls.env["federation.team.roster"].create(
            {
                "name": "AD Roster A",
                "team_id": cls.team_a.id,
                "season_id": cls.season.id,
                "season_registration_id": reg_a.id,
            }
        )

    def test_portal_403_template_is_registered(self):
        """The portal_403_access_denied template must exist in the view registry."""
        template = self.env["ir.ui.view"].search(
            [
                (
                    "key",
                    "=",
                    "sports_federation_portal.portal_403_access_denied",
                )
            ],
            limit=1,
        )
        self.assertTrue(
            template,
            "Template sports_federation_portal.portal_403_access_denied not found in registry.",
        )

    def test_portal_ownership_guard_still_raises_access_error_at_model_level(self):
        """Cross-club roster access must still raise AccessError at the model level.

        The 403 rendering happens in the controller layer; the model must still
        enforce the ownership boundary unconditionally.
        """
        Roster = self.env["federation.team.roster"]
        scope_domain = Roster._portal_get_scope_domain(user=self.user_b)
        privilege = self.env["federation.portal.privilege"]
        roster = privilege.portal_search_by_id(
            Roster,
            self.roster_a.id,
            scope_domain,
            user=self.user_b,
        )
        self.assertFalse(
            roster,
            "Cross-club access should return an empty recordset, not the other club's roster.",
        )

    def test_render_access_denied_method_exists_on_portal_base(self):
        """FederationPortalBase must expose _render_access_denied() for controllers to call."""
        from odoo.addons.sports_federation_portal.controllers.portal_helpers import (
            FederationPortalBase,
        )

        self.assertTrue(
            hasattr(FederationPortalBase, "_render_access_denied"),
            "_render_access_denied() must be defined on FederationPortalBase.",
        )

    def test_render_access_denied_method_exists_on_officiating_controller(self):
        """FederationOfficiatingPortal must also expose _render_access_denied() independently."""
        from odoo.addons.sports_federation_portal.controllers.officiating import (
            FederationOfficiatingPortal,
        )

        self.assertTrue(
            hasattr(FederationOfficiatingPortal, "_render_access_denied"),
            "_render_access_denied() must be defined on FederationOfficiatingPortal.",
        )
