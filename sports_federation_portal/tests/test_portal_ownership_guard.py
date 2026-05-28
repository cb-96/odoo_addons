"""Tests that the portal ownership boundary blocks cross-club ID guessing.

These tests directly exercise the ``federation.portal.privilege`` service
methods and the model-level ``_portal_get_scope_domain`` / ``_portal_assert_*``
helpers to prove that a portal user cannot access records belonging to another
club by guessing their database ID.

The suite is intentionally narrow: it proves *access denial*, not the full
functional flows (those live in ``test_roster_portal_access.py``).
"""

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestPortalOwnershipGuard(TransactionCase):
    """Ownership guard: portal_search_by_id blocks cross-club ID guessing."""

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
                "name": "Guard Test Season",
                "code": "GTSA",
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
            }
        )
        cls.club_a = cls.env["federation.club"].create(
            {"name": "Guard Club A", "code": "GCA"}
        )
        cls.club_b = cls.env["federation.club"].create(
            {"name": "Guard Club B", "code": "GCB"}
        )
        cls.team_a = cls.env["federation.team"].create(
            {"name": "Guard Team A", "club_id": cls.club_a.id, "code": "GTA"}
        )
        cls.team_b = cls.env["federation.team"].create(
            {"name": "Guard Team B", "club_id": cls.club_b.id, "code": "GTB"}
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

        cls.user_a = _make_user("Guard User A", "guard.a@example.com")
        cls.user_b = _make_user("Guard User B", "guard.b@example.com")

        cls.env["federation.club.representative"].create(
            {
                "club_id": cls.club_a.id,
                "partner_id": cls.user_a.partner_id.id,
                "user_id": cls.user_a.id,
                "role_type_id": cls.role_type.id,
            }
        )
        cls.env["federation.club.representative"].create(
            {
                "club_id": cls.club_b.id,
                "partner_id": cls.user_b.partner_id.id,
                "user_id": cls.user_b.id,
                "role_type_id": cls.role_type.id,
            }
        )

        # Create a confirmed registration for team_a so we can create a roster
        cls.reg_a = cls.env["federation.season.registration"].create(
            {"season_id": cls.season.id, "team_id": cls.team_a.id}
        )
        cls.reg_a.action_confirm()
        cls.reg_b = cls.env["federation.season.registration"].create(
            {"season_id": cls.season.id, "team_id": cls.team_b.id}
        )
        cls.reg_b.action_confirm()

        cls.roster_a = cls.env["federation.team.roster"].create(
            {
                "name": "Guard Roster A",
                "team_id": cls.team_a.id,
                "season_id": cls.season.id,
                "season_registration_id": cls.reg_a.id,
            }
        )
        cls.roster_b = cls.env["federation.team.roster"].create(
            {
                "name": "Guard Roster B",
                "team_id": cls.team_b.id,
                "season_id": cls.season.id,
                "season_registration_id": cls.reg_b.id,
            }
        )

    # ------------------------------------------------------------------
    # portal_search_by_id — cross-club ID guessing is blocked
    # ------------------------------------------------------------------

    def test_portal_search_by_id_blocks_cross_club_roster(self):
        """portal_search_by_id returns empty when the ID belongs to another club."""
        Roster = self.env["federation.team.roster"]
        PortalPrivilege = self.env["federation.portal.privilege"]

        # user_a's scope only covers club_a / team_a
        scope_a = Roster._portal_get_scope_domain(user=self.user_a)

        # roster_a is owned by club_a — user_a should find it
        found = PortalPrivilege.portal_search_by_id(
            Roster, self.roster_a.id, scope_a, user=self.user_a
        )
        self.assertTrue(found, "User A must be able to access their own roster by ID")
        self.assertEqual(found.id, self.roster_a.id)

        # roster_b is owned by club_b — user_a must NOT find it by guessing the ID
        not_found = PortalPrivilege.portal_search_by_id(
            Roster, self.roster_b.id, scope_a, user=self.user_a
        )
        self.assertFalse(
            not_found,
            "User A must not be able to access User B's roster by guessing the ID",
        )

    def test_portal_search_by_id_blocks_cross_club_registration(self):
        """portal_search_by_id blocks cross-club season registration ID guessing."""
        Registration = self.env["federation.season.registration"]
        PortalPrivilege = self.env["federation.portal.privilege"]
        Roster = self.env["federation.team.roster"]

        # user_a's registration scope
        scope_a = Roster._portal_get_registration_scope_domain(user=self.user_a)

        # Own registration — visible
        found = PortalPrivilege.portal_search_by_id(
            Registration, self.reg_a.id, scope_a, user=self.user_a
        )
        self.assertTrue(found)

        # Other club's registration — blocked
        not_found = PortalPrivilege.portal_search_by_id(
            Registration, self.reg_b.id, scope_a, user=self.user_a
        )
        self.assertFalse(not_found)

    # ------------------------------------------------------------------
    # _assert_portal_owns — new convenience wrapper
    # ------------------------------------------------------------------

    def test_assert_portal_owns_passes_for_own_record(self):
        """_assert_portal_owns succeeds when the record is in the user's scope."""
        Roster = self.env["federation.team.roster"]
        PortalPrivilege = self.env["federation.portal.privilege"]
        scope_a = Roster._portal_get_scope_domain(user=self.user_a)

        # Should not raise
        result = PortalPrivilege._assert_portal_owns(
            self.roster_a, scope_a, user=self.user_a
        )
        self.assertTrue(result)

    def test_assert_portal_owns_raises_for_cross_club_record(self):
        """_assert_portal_owns raises AccessError for a cross-club record."""
        Roster = self.env["federation.team.roster"]
        PortalPrivilege = self.env["federation.portal.privilege"]
        scope_a = Roster._portal_get_scope_domain(user=self.user_a)

        with self.assertRaises(AccessError):
            PortalPrivilege._assert_portal_owns(
                self.roster_b, scope_a, user=self.user_a
            )

    def test_portal_write_requires_explicit_scope_domain(self):
        """portal_write must fail closed when callers omit a scope domain."""
        PortalPrivilege = self.env["federation.portal.privilege"]
        with self.assertRaises(AccessError):
            PortalPrivilege.portal_write(
                self.roster_a,
                {"notes": "Scoped write required"},
                user=self.user_a,
            )

    def test_portal_call_requires_explicit_scope_domain(self):
        """portal_call must fail closed when callers omit a scope domain."""
        PortalPrivilege = self.env["federation.portal.privilege"]
        with self.assertRaises(AccessError):
            PortalPrivilege.portal_call(
                self.roster_a,
                "name_get",
                user=self.user_a,
            )

    # ------------------------------------------------------------------
    # _portal_assert_scope_access — model-level ownership assertion
    # ------------------------------------------------------------------

    def test_portal_assert_scope_access_blocks_cross_club(self):
        """_portal_assert_scope_access raises AccessError for a cross-club roster."""
        with self.assertRaises(AccessError):
            self.roster_b._portal_assert_scope_access(user=self.user_a)

    def test_portal_assert_scope_access_passes_for_own_roster(self):
        """_portal_assert_scope_access succeeds for a roster owned by the user's club."""
        # Should not raise
        self.roster_a._portal_assert_scope_access(user=self.user_a)

    # ------------------------------------------------------------------
    # _portal_assert_registration_access — registration ownership assertion
    # ------------------------------------------------------------------

    def test_portal_assert_registration_access_blocks_cross_club(self):
        """_portal_assert_registration_access raises AccessError cross-club."""
        with self.assertRaises(AccessError):
            self.env["federation.team.roster"]._portal_assert_registration_access(
                self.reg_b, user=self.user_a
            )

    def test_portal_assert_registration_access_passes_for_own_registration(self):
        """_portal_assert_registration_access succeeds for the user's own registration."""
        result = self.env["federation.team.roster"]._portal_assert_registration_access(
            self.reg_a, user=self.user_a
        )
        self.assertTrue(result)

    # ------------------------------------------------------------------
    # No-scope user — everything is blocked
    # ------------------------------------------------------------------

    def test_user_with_no_club_scope_gets_false_domain(self):
        """A portal user with no representative link gets the deny-all domain."""
        no_club_user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Guard No Club",
                    "login": "guard.noclub@example.com",
                    "email": "guard.noclub@example.com",
                    "group_ids": [(6, 0, [self.portal_group.id])],
                }
            )
        )
        Roster = self.env["federation.team.roster"]
        scope = Roster._portal_get_scope_domain(user=no_club_user)
        self.assertEqual(
            scope,
            [("id", "=", False)],
            "User with no club scope must receive the deny-all domain",
        )
        # Searching with this domain returns nothing
        result = self.env["federation.portal.privilege"].portal_search(
            Roster, scope, user=no_club_user
        )
        self.assertFalse(result)
