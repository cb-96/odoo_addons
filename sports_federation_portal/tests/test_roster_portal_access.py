from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestRosterPortalAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.portal_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        cls.role_type = cls.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )
        cls.coach_role_type = cls.env.ref("sports_federation_portal.role_type_coach")
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Portal Roster Season",
                "code": "PRS2",
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
            }
        )
        cls.club_a = cls.env["federation.club"].create(
            {
                "name": "Portal Roster Club A",
                "code": "PRCA",
            }
        )
        cls.club_b = cls.env["federation.club"].create(
            {
                "name": "Portal Roster Club B",
                "code": "PRCB",
            }
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "Portal Roster Team A",
                "club_id": cls.club_a.id,
                "code": "PRTA",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "Portal Roster Team B",
                "club_id": cls.club_b.id,
                "code": "PRTB",
            }
        )
        cls.team_a_reserve = cls.env["federation.team"].create(
            {
                "name": "Portal Roster Team A Reserve",
                "club_id": cls.club_a.id,
                "code": "PRTR",
            }
        )
        cls.user_a = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Portal Roster User A",
                    "login": "portal.roster.a@example.com",
                    "email": "portal.roster.a@example.com",
                    "group_ids": [(6, 0, [cls.portal_group.id])],
                }
            )
        )
        cls.user_b = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Portal Roster User B",
                    "login": "portal.roster.b@example.com",
                    "email": "portal.roster.b@example.com",
                    "group_ids": [(6, 0, [cls.portal_group.id])],
                }
            )
        )
        cls.coach_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Portal Coach User",
                    "login": "portal.coach@example.com",
                    "email": "portal.coach@example.com",
                    "group_ids": [(6, 0, [cls.portal_group.id])],
                }
            )
        )
        cls.inactive_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Portal Inactive User",
                    "login": "portal.inactive@example.com",
                    "email": "portal.inactive@example.com",
                    "group_ids": [(6, 0, [cls.portal_group.id])],
                }
            )
        )
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
        cls.env["federation.club.representative"].create(
            {
                "club_id": cls.club_a.id,
                "team_id": cls.team_a.id,
                "partner_id": cls.coach_user.partner_id.id,
                "user_id": cls.coach_user.id,
                "role_type_id": cls.coach_role_type.id,
            }
        )
        cls.env["federation.club.representative"].create(
            {
                "club_id": cls.club_a.id,
                "partner_id": cls.inactive_user.partner_id.id,
                "user_id": cls.inactive_user.id,
                "role_type_id": cls.role_type.id,
                "date_end": "2024-12-31",
            }
        )

        cls.player_a = cls.env["federation.player"].create(
            {
                "first_name": "Portal",
                "last_name": "Roster A",
                "gender": "male",
                "club_id": cls.club_a.id,
            }
        )
        cls.player_b = cls.env["federation.player"].create(
            {
                "first_name": "Portal",
                "last_name": "Roster B",
                "gender": "male",
                "club_id": cls.club_b.id,
            }
        )

        cls.registration_a = cls.env["federation.season.registration"].create(
            {
                "season_id": cls.season.id,
                "team_id": cls.team_a.id,
                "user_id": cls.user_a.id,
            }
        )
        cls.registration_a.action_confirm()
        cls.registration_a_reserve = cls.env["federation.season.registration"].create(
            {
                "season_id": cls.season.id,
                "team_id": cls.team_a_reserve.id,
                "user_id": cls.user_a.id,
            }
        )
        cls.registration_a_reserve.action_confirm()
        cls.registration_b = cls.env["federation.season.registration"].create(
            {
                "season_id": cls.season.id,
                "team_id": cls.team_b.id,
                "user_id": cls.user_b.id,
            }
        )
        cls.registration_b.action_confirm()

        cls.roster_a = cls.env["federation.team.roster"].create(
            {
                "name": "Portal Roster A",
                "team_id": cls.team_a.id,
                "season_id": cls.season.id,
                "season_registration_id": cls.registration_a.id,
            }
        )
        cls.roster_a_reserve = cls.env["federation.team.roster"].create(
            {
                "name": "Portal Roster A Reserve",
                "team_id": cls.team_a_reserve.id,
                "season_id": cls.season.id,
                "season_registration_id": cls.registration_a_reserve.id,
            }
        )
        cls.roster_b = cls.env["federation.team.roster"].create(
            {
                "name": "Portal Roster B",
                "team_id": cls.team_b.id,
                "season_id": cls.season.id,
                "season_registration_id": cls.registration_b.id,
            }
        )
        cls.env["federation.team.roster.line"].create(
            {
                "roster_id": cls.roster_a.id,
                "player_id": cls.player_a.id,
            }
        )
        cls.env["federation.team.roster.line"].create(
            {
                "roster_id": cls.roster_b.id,
                "player_id": cls.player_b.id,
            }
        )
        cls.roster_a.action_activate()
        cls.roster_b.action_activate()

        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Portal Roster Tournament",
                "code": "PRT2",
                "season_id": cls.season.id,
                "date_start": "2025-06-01",
            }
        )
        cls.match = (
            cls.env["federation.match"]
            .with_context(skip_auto_match_sheets=True)
            .create(
                {
                    "tournament_id": cls.tournament.id,
                    "home_team_id": cls.team_a.id,
                    "away_team_id": cls.team_b.id,
                    "date_scheduled": "2025-06-12 18:00:00",
                }
            )
        )
        cls.sheet_a = cls.env["federation.match.sheet"].create(
            {
                "name": "Portal Sheet A",
                "match_id": cls.match.id,
                "team_id": cls.team_a.id,
                "roster_id": cls.roster_a.id,
                "side": "home",
            }
        )
        cls.sheet_b = cls.env["federation.match.sheet"].create(
            {
                "name": "Portal Sheet B",
                "match_id": cls.match.id,
                "team_id": cls.team_b.id,
                "roster_id": cls.roster_b.id,
                "side": "away",
            }
        )

    def test_portal_user_only_sees_own_rosters_match_sheets_and_audit(self):
        """Test that portal user only sees own rosters match sheets and audit."""
        visible_rosters = (
            self.env["federation.team.roster"].with_user(self.user_a).search([])
        )
        self.assertIn(self.roster_a, visible_rosters)
        self.assertNotIn(self.roster_b, visible_rosters)

        visible_sheets = (
            self.env["federation.match.sheet"].with_user(self.user_a).search([])
        )
        self.assertIn(self.sheet_a, visible_sheets)
        self.assertNotIn(self.sheet_b, visible_sheets)

        visible_audits = (
            self.env["federation.participation.audit"].with_user(self.user_a).search([])
        )
        self.assertTrue(visible_audits)
        self.assertTrue(
            all(event.team_id.club_id == self.club_a for event in visible_audits)
        )

    def test_team_scoped_coach_only_sees_assigned_team_records(self):
        """Test that team scoped coach only sees assigned team records."""
        self.assertEqual(self.coach_user.portal_team_scope_ids, self.team_a)
        self.assertFalse(self.coach_user.portal_club_scope_ids)

        visible_teams = (
            self.env["federation.team"].with_user(self.coach_user).search([])
        )
        self.assertIn(self.team_a, visible_teams)
        self.assertNotIn(self.team_a_reserve, visible_teams)
        self.assertNotIn(self.team_b, visible_teams)

        visible_rosters = (
            self.env["federation.team.roster"].with_user(self.coach_user).search([])
        )
        self.assertIn(self.roster_a, visible_rosters)
        self.assertNotIn(self.roster_a_reserve, visible_rosters)
        self.assertNotIn(self.roster_b, visible_rosters)

        visible_sheets = (
            self.env["federation.match.sheet"].with_user(self.coach_user).search([])
        )
        self.assertIn(self.sheet_a, visible_sheets)
        self.assertNotIn(self.sheet_b, visible_sheets)

    def test_inactive_representative_loses_current_match_day_scope(self):
        """Inactive representative rows must not preserve live portal match-day access."""
        self.assertIn(self.club_a, self.inactive_user.represented_club_ids)
        self.assertFalse(self.inactive_user.portal_club_scope_ids)
        self.assertFalse(self.inactive_user.portal_team_scope_ids)

        visible_teams = (
            self.env["federation.team"].with_user(self.inactive_user).search([])
        )
        visible_rosters = (
            self.env["federation.team.roster"].with_user(self.inactive_user).search([])
        )
        visible_sheets = (
            self.env["federation.match.sheet"].with_user(self.inactive_user).search([])
        )

        self.assertFalse(visible_teams)
        self.assertFalse(visible_rosters)
        self.assertFalse(visible_sheets)
        self.assertFalse(
            self.tournament._portal_has_workspace_access(user=self.inactive_user)
        )

        with self.assertRaises(AccessError):
            self.roster_a._portal_assert_scope_access(user=self.inactive_user)
        with self.assertRaises(AccessError):
            self.sheet_a._portal_assert_review_access(user=self.inactive_user)

    def test_team_scoped_coach_can_prepare_and_submit_assigned_sheet(self):
        """Test that team scoped coach can prepare and submit assigned sheet."""
        self.sheet_a._portal_update_preparation(
            user=self.coach_user,
            values={
                "coach_name": "Coach Portal",
                "manager_name": "Manager Portal",
                "notes": "Ready for kickoff.",
            },
        )
        self.sheet_a.invalidate_recordset()
        self.assertEqual(self.sheet_a.coach_name, "Coach Portal")
        self.assertEqual(self.sheet_a.manager_name, "Manager Portal")
        self.assertEqual(self.sheet_a.notes, "Ready for kickoff.")

        self.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": self.sheet_a.id,
                "player_id": self.player_a.id,
                "roster_line_id": self.roster_a.line_ids[:1].id,
                "is_starter": True,
            }
        )
        self.assertTrue(self.sheet_a.ready_for_submission)

        self.sheet_a._portal_action_submit(user=self.coach_user)
        self.sheet_a.invalidate_recordset()
        self.assertEqual(self.sheet_a.state, "submitted")

    def test_portal_user_cannot_modify_roster_records(self):
        """Test that portal user cannot modify roster records."""
        with self.assertRaises(AccessError):
            self.roster_a.with_user(self.user_a).write({"notes": "Not allowed"})
        with self.assertRaises(AccessError):
            self.sheet_a.with_user(self.user_a).write({"notes": "Not allowed"})

    def test_portal_user_can_create_roster_for_confirmed_registration(self):
        """Test that portal user can create roster for confirmed registration."""
        team_c = self.env["federation.team"].create(
            {
                "name": "Portal Roster Team C",
                "club_id": self.club_a.id,
                "code": "PRTC",
            }
        )
        registration_c = self.env["federation.season.registration"].create(
            {
                "season_id": self.season.id,
                "team_id": team_c.id,
                "user_id": self.user_a.id,
            }
        )
        registration_c.action_confirm()

        roster = self.env[
            "federation.team.roster"
        ]._portal_create_roster_for_registration(
            registration_c,
            user=self.user_a,
        )

        self.assertEqual(roster.team_id, team_c)
        self.assertEqual(roster.season_registration_id, registration_c)
        self.assertEqual(roster.create_uid, self.user_a)

    def test_team_scoped_coach_reuses_primary_roster_only_for_assigned_team(self):
        """Team-scoped portal helpers must stay pinned to the assigned team."""
        roster = self.env[
            "federation.team.roster"
        ]._portal_get_primary_roster_for_registration(
            self.registration_a,
            user=self.coach_user,
        )

        self.assertEqual(roster, self.roster_a)

        with self.assertRaises(AccessError):
            self.env[
                "federation.team.roster"
            ]._portal_get_primary_roster_for_registration(
                self.registration_a_reserve,
                user=self.coach_user,
            )

    def test_team_scoped_coach_cannot_manage_same_club_other_team_roster(self):
        """Team-scoped representatives cannot mutate same-club foreign-team rosters."""
        with self.assertRaises(AccessError):
            self.roster_a_reserve._portal_update_roster(
                user=self.coach_user,
                values={"notes": "Not allowed"},
            )

    def test_portal_user_cannot_create_roster_without_confirmation_or_for_other_club(
        self,
    ):
        """Test that portal user cannot create roster without confirmation or for other club."""
        draft_team = self.env["federation.team"].create(
            {
                "name": "Portal Draft Team",
                "club_id": self.club_a.id,
                "code": "PRTD",
            }
        )
        draft_registration = self.env["federation.season.registration"].create(
            {
                "season_id": self.season.id,
                "team_id": draft_team.id,
                "user_id": self.user_a.id,
            }
        )

        with self.assertRaises(ValidationError):
            self.env["federation.team.roster"]._portal_create_roster_for_registration(
                draft_registration,
                user=self.user_a,
            )

        with self.assertRaises(AccessError):
            self.env["federation.team.roster"]._portal_create_roster_for_registration(
                self.registration_b,
                user=self.user_a,
            )

    def test_portal_user_can_manage_owned_roster_with_portal_helpers(self):
        """Test that portal user can manage owned roster with portal helpers."""
        self.roster_a._portal_update_roster(
            user=self.user_a,
            values={"notes": "Updated through portal helper"},
        )
        self.roster_a.invalidate_recordset()
        self.assertEqual(self.roster_a.notes, "Updated through portal helper")

        player_c = self.env["federation.player"].create(
            {
                "first_name": "Portal",
                "last_name": "Roster C",
                "gender": "male",
                "club_id": self.club_a.id,
                "team_ids": [(4, self.team_a.id)],
            }
        )
        line = self.env["federation.team.roster.line"]._portal_create_line(
            self.roster_a,
            values={
                "player_id": player_c.id,
                "jersey_number": "9",
            },
            user=self.user_a,
        )
        self.assertEqual(line.create_uid, self.user_a)

        line._portal_update_line(
            values={
                "jersey_number": "10",
                "status": "active",
            },
            user=self.user_a,
        )
        line.invalidate_recordset()
        self.assertEqual(line.jersey_number, "10")
        self.assertEqual(line.status, "active")

        line_id = line.id
        line._portal_delete_line(user=self.user_a)
        self.assertFalse(
            self.env["federation.team.roster.line"].browse(line_id).exists()
        )

    def test_portal_user_can_reopen_closed_roster_with_helper(self):
        """Portal helpers should allow reopening a closed owned roster."""
        self.roster_a._portal_action_close(user=self.user_a)
        self.roster_a.invalidate_recordset()
        self.assertEqual(self.roster_a.status, "closed")

        self.roster_a._portal_action_reopen(user=self.user_a)
        self.roster_a.invalidate_recordset()
        self.assertEqual(self.roster_a.status, "active")

    def test_portal_user_cannot_reopen_non_closed_roster(self):
        """Portal reopen helper should enforce closed-state precondition."""
        with self.assertRaises(ValidationError):
            self.roster_a._portal_action_reopen(user=self.user_a)

    def test_portal_player_picker_filters_by_team_gender(self):
        """Portal line creation must enforce the same gender filter as the picker."""
        women_team = self.env["federation.team"].create(
            {
                "name": "Portal Women Team",
                "club_id": self.club_a.id,
                "code": "PRTW",
                "gender": "female",
            }
        )
        women_registration = self.env["federation.season.registration"].create(
            {
                "season_id": self.season.id,
                "team_id": women_team.id,
                "user_id": self.user_a.id,
            }
        )
        women_registration.action_confirm()
        women_roster = self.env["federation.team.roster"].create(
            {
                "name": "Portal Women Roster",
                "team_id": women_team.id,
                "season_id": self.season.id,
                "season_registration_id": women_registration.id,
            }
        )
        female_player = self.env["federation.player"].create(
            {
                "first_name": "Portal",
                "last_name": "Roster D",
                "gender": "female",
                "club_id": self.club_a.id,
            }
        )
        male_player = self.env["federation.player"].create(
            {
                "first_name": "Portal",
                "last_name": "Roster E",
                "gender": "male",
                "club_id": self.club_a.id,
            }
        )

        available_players = self.env[
            "federation.team.roster.line"
        ]._portal_get_available_players(women_roster, user=self.user_a)

        self.assertIn(female_player, available_players)
        self.assertNotIn(male_player, available_players)

        line = self.env["federation.team.roster.line"]._portal_create_line(
            women_roster,
            values={
                "player_id": str(female_player.id),
                "jersey_number": "7",
            },
            user=self.user_a,
        )
        self.assertEqual(line.player_id, female_player)

        with self.assertRaises(ValidationError):
            self.env["federation.team.roster.line"]._portal_create_line(
                women_roster,
                values={
                    "player_id": str(male_player.id),
                    "jersey_number": "8",
                },
                user=self.user_a,
            )

    def test_portal_player_picker_stays_within_query_budget(self):
        """Roster player availability should not regress into an expensive portal lookup."""
        with self.assertQueryCount(9):
            available_players = self.env[
                "federation.team.roster.line"
            ]._portal_get_available_players(self.roster_a, user=self.user_a)

        # player_a is already on roster_a (class fixture), so must be excluded
        self.assertNotIn(self.player_a, available_players)

    def test_portal_player_picker_excludes_players_already_on_roster(self):
        """Players already on a roster must not appear in the available player picker."""
        # Create a fresh player not yet on any roster
        fresh_player = self.env["federation.player"].create(
            {
                "first_name": "Portal",
                "last_name": "Fresh Picker",
                "gender": "male",
                "club_id": self.club_a.id,
            }
        )

        # fresh_player should appear; player_a is already on roster_a (class fixture)
        available_before = self.env[
            "federation.team.roster.line"
        ]._portal_get_available_players(self.roster_a, user=self.user_a)
        self.assertNotIn(self.player_a, available_before)
        self.assertIn(fresh_player, available_before)

        # Add fresh_player to the roster
        self.env["federation.team.roster.line"]._portal_create_line(
            self.roster_a,
            values={"player_id": str(fresh_player.id)},
            user=self.user_a,
        )

        # After adding: fresh_player must now be excluded too
        available_after = self.env[
            "federation.team.roster.line"
        ]._portal_get_available_players(self.roster_a, user=self.user_a)
        self.assertNotIn(self.player_a, available_after)
        self.assertNotIn(fresh_player, available_after)

    def test_portal_license_picker_and_submission_share_scope_domain(self):
        """Portal line licenses must use the same roster and player scope on read and write."""
        licensed_player = self.env["federation.player"].create(
            {
                "first_name": "Portal",
                "last_name": "Licensed Player",
                "gender": "male",
                "club_id": self.club_a.id,
            }
        )
        valid_license = self.env["federation.player.license"].create(
            {
                "name": "PORTAL-LIC-A",
                "player_id": licensed_player.id,
                "season_id": self.season.id,
                "club_id": self.club_a.id,
                "issue_date": "2025-01-01",
                "expiry_date": "2025-12-31",
                "state": "active",
            }
        )
        foreign_license = self.env["federation.player.license"].create(
            {
                "name": "PORTAL-LIC-B",
                "player_id": self.player_b.id,
                "season_id": self.season.id,
                "club_id": self.club_b.id,
                "issue_date": "2025-01-01",
                "expiry_date": "2025-12-31",
                "state": "active",
            }
        )

        available_licenses = self.env[
            "federation.team.roster.line"
        ]._portal_get_available_licenses(
            self.roster_a,
            user=self.user_a,
            player=licensed_player,
        )

        self.assertIn(valid_license, available_licenses)
        self.assertNotIn(foreign_license, available_licenses)

        with self.assertRaises(ValidationError):
            self.env["federation.team.roster.line"]._portal_create_line(
                self.roster_a,
                values={
                    "player_id": str(licensed_player.id),
                    "license_id": str(foreign_license.id),
                    "jersey_number": "11",
                },
                user=self.user_a,
            )

        line = self.env["federation.team.roster.line"]._portal_create_line(
            self.roster_a,
            values={
                "player_id": str(licensed_player.id),
                "license_id": str(valid_license.id),
                "jersey_number": "12",
            },
            user=self.user_a,
        )

        self.assertEqual(line.license_id, valid_license)

    def test_portal_update_preparation_links_roster(self):
        """_portal_update_preparation must allow portal users to link a same-team roster."""
        # Create a sheet without a roster pre-linked (side=other avoids the unique-per-match constraint)
        no_roster_sheet = self.env["federation.match.sheet"].create(
            {
                "name": "Portal Sheet No Roster",
                "match_id": self.match.id,
                "team_id": self.team_a.id,
                "side": "other",
            }
        )
        self.assertFalse(no_roster_sheet.roster_id)

        # Linking an active same-team roster must succeed
        no_roster_sheet._portal_update_preparation(
            user=self.user_a,
            values={"roster_id": str(self.roster_a.id)},
        )
        no_roster_sheet.invalidate_recordset()
        self.assertEqual(no_roster_sheet.roster_id, self.roster_a)

    def test_portal_update_preparation_rejects_foreign_team_roster(self):
        """_portal_update_preparation must reject a roster that belongs to a different team."""
        no_roster_sheet = self.env["federation.match.sheet"].create(
            {
                "name": "Portal Sheet Foreign Roster",
                "match_id": self.match.id,
                "team_id": self.team_a.id,
                "side": "other",
            }
        )
        # roster_b belongs to team_b — must be silently ignored (not linked)
        no_roster_sheet._portal_update_preparation(
            user=self.user_a,
            values={"roster_id": str(self.roster_b.id)},
        )
        no_roster_sheet.invalidate_recordset()
        self.assertFalse(no_roster_sheet.roster_id)
