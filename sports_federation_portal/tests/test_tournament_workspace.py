from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestTournamentWorkspace(TransactionCase):
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
                "name": "Workspace Season",
                "code": "WSS",
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
            }
        )
        cls.competition = cls.env["federation.competition"].create(
            {
                "name": "Workspace League",
                "code": "WSL",
                "competition_type": "league",
            }
        )

        cls.club_a = cls.env["federation.club"].create(
            {
                "name": "Workspace Club A",
                "code": "WSCA",
            }
        )
        cls.club_b = cls.env["federation.club"].create(
            {
                "name": "Workspace Club B",
                "code": "WSCB",
            }
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "Workspace Team A",
                "club_id": cls.club_a.id,
                "code": "WSTA",
                "category": "senior",
                "gender": "male",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "Workspace Team B",
                "club_id": cls.club_b.id,
                "code": "WSTB",
                "category": "senior",
                "gender": "male",
            }
        )

        cls.user_a = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Workspace User A",
                    "login": "workspace.a@example.com",
                    "email": "workspace.a@example.com",
                    "group_ids": [(6, 0, [cls.portal_group.id])],
                }
            )
        )
        cls.user_b = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Workspace User B",
                    "login": "workspace.b@example.com",
                    "email": "workspace.b@example.com",
                    "group_ids": [(6, 0, [cls.portal_group.id])],
                }
            )
        )
        cls.coach_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Workspace Coach",
                    "login": "workspace.coach@example.com",
                    "email": "workspace.coach@example.com",
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

        cls.player_a = cls.env["federation.player"].create(
            {
                "first_name": "Workspace",
                "last_name": "Player",
                "gender": "male",
                "club_id": cls.club_a.id,
                "team_ids": [(4, cls.team_a.id)],
            }
        )

        cls.open_tournament = cls.env["federation.tournament"].create(
            {
                "name": "Workspace Open Tournament",
                "code": "WSOT",
                "season_id": cls.season.id,
                "date_start": "2025-06-01",
                "state": "open",
                "category": "senior",
                "gender": "male",
            }
        )
        cls.live_tournament = cls.env["federation.tournament"].create(
            {
                "name": "Workspace Live Tournament",
                "code": "WSLT",
                "season_id": cls.season.id,
                "competition_id": cls.competition.id,
                "date_start": "2025-07-01",
                "state": "in_progress",
                "category": "senior",
                "gender": "male",
            }
        )
        cls.closed_tournament = cls.env["federation.tournament"].create(
            {
                "name": "Workspace Closed Tournament",
                "code": "WSCT",
                "season_id": cls.season.id,
                "date_start": "2025-08-01",
                "state": "closed",
                "category": "senior",
                "gender": "male",
            }
        )

        cls.open_registration = cls.env["federation.tournament.registration"].create(
            {
                "tournament_id": cls.open_tournament.id,
                "team_id": cls.team_a.id,
                "user_id": cls.user_a.id,
            }
        )
        cls.open_registration.action_submit()

        cls.live_registration = cls.env["federation.tournament.registration"].create(
            {
                "tournament_id": cls.live_tournament.id,
                "team_id": cls.team_a.id,
                "user_id": cls.user_a.id,
            }
        )
        cls.live_registration.action_submit()
        cls.live_registration.action_confirm()
        cls.participant = cls.live_registration.participant_id

        cls.competition_roster = cls.participant._get_readiness_roster()
        cls.roster_line = cls.env["federation.team.roster.line"].create(
            {
                "roster_id": cls.competition_roster.id,
                "player_id": cls.player_a.id,
                "status": "active",
            }
        )
        cls.competition_roster.action_activate()
        cls.participant.action_confirm()

        cls.generic_roster = cls.env["federation.team.roster"].create(
            {
                "name": "Workspace Generic Roster",
                "team_id": cls.team_a.id,
                "season_id": cls.season.id,
            }
        )

        cls.future_match = (
            cls.env["federation.match"]
            .with_context(skip_auto_match_sheets=True)
            .create(
                {
                    "tournament_id": cls.live_tournament.id,
                    "home_team_id": cls.team_a.id,
                    "away_team_id": cls.team_b.id,
                    "date_scheduled": "2025-07-10 18:00:00",
                    "state": "scheduled",
                }
            )
        )
        cls.future_sheet = cls.env["federation.match.sheet"].create(
            {
                "name": "Workspace Future Sheet",
                "match_id": cls.future_match.id,
                "team_id": cls.team_a.id,
                "roster_id": cls.competition_roster.id,
                "side": "home",
            }
        )
        cls.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": cls.future_sheet.id,
                "player_id": cls.player_a.id,
                "roster_line_id": cls.roster_line.id,
                "is_starter": True,
            }
        )

        cls.past_match = (
            cls.env["federation.match"]
            .with_context(skip_auto_match_sheets=True)
            .create(
                {
                    "tournament_id": cls.live_tournament.id,
                    "home_team_id": cls.team_a.id,
                    "away_team_id": cls.team_b.id,
                    "date_scheduled": "2025-07-05 18:00:00",
                    "state": "done",
                    "home_score": 2,
                    "away_score": 1,
                    "result_state": "submitted",
                }
            )
        )
        cls.past_sheet = cls.env["federation.match.sheet"].create(
            {
                "name": "Workspace Past Sheet",
                "match_id": cls.past_match.id,
                "team_id": cls.team_a.id,
                "roster_id": cls.competition_roster.id,
                "side": "home",
            }
        )
        cls.env["federation.match.sheet.line"].create(
            {
                "match_sheet_id": cls.past_sheet.id,
                "player_id": cls.player_a.id,
                "roster_line_id": cls.roster_line.id,
                "is_starter": True,
            }
        )
        cls.past_sheet.write({"state": "approved"})

    def _workspace_entry(self, entries, tournament, team):
        """Exercise workspace entry."""
        for entry in entries:
            if entry["tournament"] == tournament and entry["team"] == team:
                return entry
        self.fail("Workspace entry not found")

    def test_workspace_entries_summarize_active_tournament_operations(self):
        """Test that workspace entries summarize active tournament operations."""
        entries = self.env["federation.tournament"]._portal_get_workspace_entries(
            user=self.user_a
        )

        self.assertEqual(len(entries), 2)

        open_entry = self._workspace_entry(entries, self.open_tournament, self.team_a)
        self.assertEqual(
            open_entry["registration_checkpoint"]["label"],
            "Registration under review",
        )
        self.assertEqual(open_entry["roster"], self.generic_roster)
        self.assertEqual(
            open_entry["roster_checkpoint"]["label"],
            "Draft roster needs attention",
        )

        live_entry = self._workspace_entry(entries, self.live_tournament, self.team_a)
        self.assertEqual(live_entry["participant"], self.participant)
        self.assertEqual(
            live_entry["registration_checkpoint"]["label"],
            "Participant confirmed",
        )
        self.assertEqual(live_entry["roster"], self.competition_roster)
        self.assertEqual(
            live_entry["roster_checkpoint"]["label"],
            "Roster frozen by match-day activity",
        )
        self.assertEqual(live_entry["pending_match_day_count"], 1)
        self.assertEqual(len(live_entry["upcoming_match_sheets"]), 1)
        self.assertEqual(live_entry["result_follow_up_count"], 1)
        self.assertEqual(
            live_entry["result_follow_up_rows"][0]["match"], self.past_match
        )
        self.assertEqual(
            live_entry["result_follow_up_rows"][0]["sheet"], self.past_sheet
        )

    def test_workspace_entry_lookup_enforces_portal_scope(self):
        """Test that workspace entry lookup enforces portal scope."""
        own_entry = self.env[
            "federation.tournament"
        ]._portal_get_workspace_entry_for_user(
            self.live_tournament.id,
            self.team_a.id,
            user=self.user_a,
        )
        self.assertTrue(own_entry)

        other_team_entry = self.env[
            "federation.tournament"
        ]._portal_get_workspace_entry_for_user(
            self.live_tournament.id,
            self.team_b.id,
            user=self.user_a,
        )
        self.assertFalse(other_team_entry)

    def test_workspace_entry_builder_blocks_direct_cross_team_access(self):
        """Test that direct workspace reads still enforce the caller's team scope."""
        with self.assertRaises(AccessError):
            self.live_tournament._portal_get_workspace_entry(
                self.team_b,
                user=self.user_a,
            )

    def test_workspace_entry_builder_blocks_closed_tournaments(self):
        """Test that direct workspace reads stay limited to active tournaments."""
        with self.assertRaises(AccessError):
            self.closed_tournament._portal_get_workspace_entry(
                self.team_a,
                user=self.user_a,
            )

    def test_team_scoped_coach_only_sees_assigned_team_workspaces(self):
        """Test that team scoped coach only sees assigned team workspaces."""
        entries = self.env["federation.tournament"]._portal_get_workspace_entries(
            user=self.coach_user
        )

        self.assertEqual(len(entries), 2)
        self.assertTrue(all(entry["team"] == self.team_a for entry in entries))
        self.assertTrue(
            self.env["federation.tournament"]._portal_has_workspace_access(
                user=self.coach_user
            )
        )
