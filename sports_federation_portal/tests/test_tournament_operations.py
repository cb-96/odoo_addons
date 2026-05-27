from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestTournamentOperations(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.portal_group = cls.env.ref(
            "sports_federation_portal.group_federation_portal_club"
        )
        cls.role_type = cls.env.ref(
            "sports_federation_portal.role_type_competition_contact"
        )
        cls.manager_group = cls.env.ref("sports_federation_base.group_federation_manager")
        cls.validator_group = cls.env.ref(
            "sports_federation_result_control.group_result_validator"
        )

        cls.manager_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Operations Manager",
                    "login": "operations.manager@example.com",
                    "email": "operations.manager@example.com",
                    "group_ids": [(6, 0, [cls.manager_group.id])],
                }
            )
        )
        cls.submitter_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Operations Submitter",
                    "login": "operations.submitter@example.com",
                    "email": "operations.submitter@example.com",
                    "group_ids": [(6, 0, [cls.manager_group.id])],
                }
            )
        )
        cls.validator_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Operations Validator",
                    "login": "operations.validator@example.com",
                    "email": "operations.validator@example.com",
                    "group_ids": [(6, 0, [cls.manager_group.id, cls.validator_group.id])],
                }
            )
        )

        cls.club_a = cls.env["federation.club"].create(
            {"name": "Operations Club A", "code": "OPA"}
        )
        cls.club_b = cls.env["federation.club"].create(
            {"name": "Operations Club B", "code": "OPB"}
        )
        cls.club_c = cls.env["federation.club"].create(
            {"name": "Operations Club C", "code": "OPC"}
        )
        cls.club_d = cls.env["federation.club"].create(
            {"name": "Operations Club D", "code": "OPD"}
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "Operations Team A",
                "club_id": cls.club_a.id,
                "code": "OPTA",
                "category": "senior",
                "gender": "mixed",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "Operations Team B",
                "club_id": cls.club_b.id,
                "code": "OPTB",
                "category": "senior",
                "gender": "mixed",
            }
        )
        cls.team_c = cls.env["federation.team"].create(
            {
                "name": "Operations Team C",
                "club_id": cls.club_c.id,
                "code": "OPTC",
                "category": "senior",
                "gender": "mixed",
            }
        )
        cls.team_d = cls.env["federation.team"].create(
            {
                "name": "Operations Team D",
                "club_id": cls.club_d.id,
                "code": "OPTD",
                "category": "senior",
                "gender": "mixed",
            }
        )

        cls.portal_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Operations Portal User",
                    "login": "operations.portal@example.com",
                    "email": "operations.portal@example.com",
                    "group_ids": [(6, 0, [cls.portal_group.id])],
                }
            )
        )
        cls.unrelated_portal_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Operations Unrelated Portal User",
                    "login": "operations.unrelated@example.com",
                    "email": "operations.unrelated@example.com",
                    "group_ids": [(6, 0, [cls.portal_group.id])],
                }
            )
        )
        cls.out_of_scope_portal_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Operations Out Of Scope Portal User",
                    "login": "operations.out.of.scope@example.com",
                    "email": "operations.out.of.scope@example.com",
                    "group_ids": [(6, 0, [cls.portal_group.id])],
                }
            )
        )
        cls.env["federation.club.representative"].create(
            {
                "club_id": cls.club_a.id,
                "partner_id": cls.portal_user.partner_id.id,
                "user_id": cls.portal_user.id,
                "role_type_id": cls.role_type.id,
            }
        )
        cls.env["federation.club.representative"].create(
            {
                "club_id": cls.club_c.id,
                "partner_id": cls.unrelated_portal_user.partner_id.id,
                "user_id": cls.unrelated_portal_user.id,
                "role_type_id": cls.role_type.id,
            }
        )
        cls.env["federation.club.representative"].create(
            {
                "club_id": cls.club_d.id,
                "partner_id": cls.out_of_scope_portal_user.partner_id.id,
                "user_id": cls.out_of_scope_portal_user.id,
                "role_type_id": cls.role_type.id,
            }
        )

        cls.season = cls.env["federation.season"].create(
            {
                "name": "Operations Season",
                "code": "OPS",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Operations Tournament",
                "code": "OPT",
                "season_id": cls.season.id,
                "date_start": "2026-06-01",
                "state": "in_progress",
                "location": "Main Hall",
            }
        )

        venue_model = cls.env.get("federation.venue")
        playing_area_model = cls.env.get("federation.playing.area")
        cls.venue = venue_model.create({"name": "Operations Venue", "city": "Brussels"}) if venue_model else False
        cls.playing_area = (
            playing_area_model.create({"name": "Court 1", "venue_id": cls.venue.id})
            if playing_area_model and cls.venue
            else False
        )

        match_vals = {
            "tournament_id": cls.tournament.id,
            "home_team_id": cls.team_a.id,
            "away_team_id": cls.team_b.id,
        }
        if cls.venue:
            match_vals["venue_id"] = cls.venue.id
        if cls.playing_area:
            match_vals["playing_area_id"] = cls.playing_area.id

        cls.live_match = cls.env["federation.match"].create(
            dict(
                match_vals,
                date_scheduled="2026-06-14 09:00:00",
                state="in_progress",
                home_score=1,
                away_score=0,
            )
        )
        cls.missing_result_match = cls.env["federation.match"].create(
            dict(
                match_vals,
                date_scheduled="2026-06-14 10:00:00",
                state="done",
                home_score=3,
                away_score=2,
            )
        )
        cls.verified_match = cls.env["federation.match"].create(
            dict(
                match_vals,
                date_scheduled="2026-06-14 11:00:00",
                state="done",
                home_score=4,
                away_score=1,
            )
        )
        cls.foreign_match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.team_c.id,
                "away_team_id": cls.team_b.id,
                "date_scheduled": "2026-06-14 12:00:00",
                "state": "done",
                "home_score": 1,
                "away_score": 0,
            }
        )

        referee = cls.env["federation.referee"].create(
            {
                "name": "Operations Referee",
                "email": "operations.referee@example.com",
                "certification_level": "national",
            }
        )
        cls.env["federation.match.referee"].create(
            {
                "match_id": cls.live_match.id,
                "referee_id": referee.id,
                "role": "head",
                "state": "confirmed",
            }
        )

        cls.verified_match.with_user(cls.submitter_user).action_submit_result()
        cls.verified_match.with_user(cls.validator_user).action_verify_result()

    def test_manager_payload_contains_expected_summary_and_actions(self):
        payload = self.tournament._operations_get_payload(user=self.manager_user)

        self.assertEqual(payload["tournament"]["name"], self.tournament.name)
        self.assertEqual(payload["summary"]["match_count"], 4)
        self.assertEqual(payload["summary"]["now_playing_count"], 1)
        self.assertEqual(payload["summary"]["missing_result_count"], 2)
        self.assertEqual(payload["summary"]["needs_validation_count"], 1)
        self.assertGreaterEqual(payload["summary"]["action_queue_count"], 1)
        self.assertTrue(payload["matches"])
        self.assertIn("primary_action", payload["matches"][0])
        self.assertTrue(payload["action_queue"])
        self.assertTrue(payload["court_summaries"])
        self.assertIn("filters", payload)

    def test_payload_exposes_next_step_schedule_status_and_ranked_queue(self):
        payload = self.tournament._operations_get_payload(user=self.manager_user)
        matches_by_id = {match["id"]: match for match in payload["matches"]}

        self.assertEqual(
            matches_by_id[self.live_match.id]["next_step"]["key"],
            "finish",
        )
        self.assertEqual(
            matches_by_id[self.missing_result_match.id]["next_step"]["key"],
            "submit",
        )
        self.assertEqual(
            matches_by_id[self.verified_match.id]["next_step"]["key"],
            "approve",
        )
        self.assertTrue(
            matches_by_id[self.missing_result_match.id]["schedule_status"][
                "short_label"
            ]
        )
        self.assertEqual(payload["action_queue"][0]["match_id"], self.missing_result_match.id)
        court_names = {court["court_name"] for court in payload["court_summaries"]}
        if self.playing_area:
            self.assertIn(self.playing_area.name, court_names)
        else:
            self.assertIn("Unassigned court", court_names)

    def test_portal_user_can_resolve_visible_tournament(self):
        visible_tournament = self.env["federation.tournament"]._operations_get_tournament_for_user(
            self.tournament.id,
            user=self.portal_user,
        )

        self.assertEqual(visible_tournament, self.tournament)

    def test_unrelated_portal_user_cannot_resolve_foreign_tournament(self):
        hidden_tournament = self.env["federation.tournament"]._operations_get_tournament_for_user(
            self.tournament.id,
            user=self.out_of_scope_portal_user,
        )

        self.assertFalse(hidden_tournament)

    def test_manager_can_submit_result_from_operations_helper(self):
        message = self.tournament._operations_apply_action(
            self.missing_result_match,
            "submit",
            values={"home_score": 5, "away_score": 4},
            user=self.manager_user,
        )

        self.assertEqual(message, "Result submitted for checking.")
        self.assertEqual(self.missing_result_match.result_state, "submitted")
        self.assertEqual(self.missing_result_match.home_score, 5)
        self.assertEqual(self.missing_result_match.away_score, 4)

    def test_invalid_score_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.tournament._operations_apply_action(
                self.missing_result_match,
                "save_score",
                values={"home_score": -1, "away_score": 2},
                user=self.manager_user,
            )

    def test_portal_user_can_approve_verified_visible_result(self):
        portal_match = self.tournament._operations_get_match_for_user(
            self.verified_match.id,
            user=self.portal_user,
        )

        message = self.tournament._operations_apply_action(
            portal_match,
            "approve",
            user=self.portal_user,
        )

        self.assertEqual(message, "Result approved and now counts in official standings.")
        self.assertEqual(self.verified_match.result_state, "approved")
        self.assertTrue(self.verified_match.include_in_official_standings)

    def test_portal_scope_only_returns_visible_matches(self):
        payload = self.tournament._operations_get_payload(user=self.portal_user)
        match_ids = {match["id"] for match in payload["matches"]}
        queue_match_ids = {item["match_id"] for item in payload["action_queue"]}

        self.assertIn(self.live_match.id, match_ids)
        self.assertIn(self.missing_result_match.id, match_ids)
        self.assertIn(self.verified_match.id, match_ids)
        self.assertNotIn(self.foreign_match.id, match_ids)
        self.assertNotIn(self.foreign_match.id, queue_match_ids)
