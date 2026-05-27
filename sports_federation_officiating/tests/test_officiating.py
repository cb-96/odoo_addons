"""Tests for sports_federation_officiating: referees, certifications, match assignments."""

import unittest

from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestFederationReferee(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.referee = cls.env["federation.referee"].create(
            {
                "name": "Test Referee",
                "email": "ref@example.com",
                "certification_level": "national",
            }
        )

    def test_create_referee(self):
        """Test that create referee."""
        self.assertTrue(self.referee.id)
        self.assertEqual(self.referee.certification_level, "national")

    def test_certification_count(self):
        """Test that certification count."""
        self.assertEqual(self.referee.certification_count, 0)
        self.env["federation.referee.certification"].create(
            {
                "name": "CERT-001",
                "referee_id": self.referee.id,
                "level": "national",
                "issue_date": "2024-01-01",
            }
        )
        self.referee.invalidate_recordset()
        self.assertEqual(self.referee.certification_count, 1)


class TestRefereeCertification(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.referee = cls.env["federation.referee"].create(
            {
                "name": "Cert Referee",
            }
        )

    def test_create_certification(self):
        """Test that create certification."""
        cert = self.env["federation.referee.certification"].create(
            {
                "name": "CERT-002",
                "referee_id": self.referee.id,
                "level": "regional",
                "issue_date": "2024-03-01",
            }
        )
        self.assertTrue(cert.id)
        self.assertTrue(cert.active)

    def test_certification_invalid_dates(self):
        """Test that certification invalid dates."""
        with self.assertRaises(ValidationError):
            self.env["federation.referee.certification"].create(
                {
                    "name": "CERT-BAD",
                    "referee_id": self.referee.id,
                    "level": "local",
                    "issue_date": "2024-06-01",
                    "expiry_date": "2024-01-01",
                }
            )

    def test_duplicate_certification_rejected(self):
        """Test that duplicate certification rejected."""
        self.env["federation.referee.certification"].create(
            {
                "name": "CERT-003",
                "referee_id": self.referee.id,
                "level": "national",
                "issue_date": "2024-05-01",
            }
        )
        with self.assertRaises(Exception):
            self.env["federation.referee.certification"].create(
                {
                    "name": "CERT-003-DUP",
                    "referee_id": self.referee.id,
                    "level": "national",
                    "issue_date": "2024-05-01",
                }
            )
            self.env.cr.flush()


class TestMatchReferee(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Ref Test Club",
                "code": "RTC",
            }
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "Ref Team A",
                "club_id": cls.club.id,
                "code": "RTA",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "Ref Team B",
                "club_id": cls.club.id,
                "code": "RTB",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Ref Season",
                "code": "REFS24",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Ref Tournament",
                "code": "RTOUR",
                "season_id": cls.season.id,
                "date_start": "2024-06-01",
            }
        )
        cls.match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.team_a.id,
                "away_team_id": cls.team_b.id,
                "state": "draft",
            }
        )
        cls.referee = cls.env["federation.referee"].create(
            {
                "name": "Match Referee",
                "certification_level": "national",
            }
        )

    def test_assign_referee_to_match(self):
        """Test that assign referee to match."""
        assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        self.assertTrue(assignment.id)
        self.assertEqual(assignment.state, "draft")
        self.assertEqual(assignment.tournament_id, self.tournament)

    def test_assignment_state_transitions(self):
        """Test that assignment state transitions."""
        assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        assignment.action_confirm()
        self.assertEqual(assignment.state, "confirmed")
        assignment.action_done()
        self.assertEqual(assignment.state, "done")
        assignment.action_draft()
        self.assertEqual(assignment.state, "draft")
        assignment.action_cancel()
        self.assertEqual(assignment.state, "cancelled")

    def test_duplicate_role_rejected(self):
        """Test that duplicate role rejected."""
        self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        with self.assertRaises(Exception):
            self.env["federation.match.referee"].create(
                {
                    "match_id": self.match.id,
                    "referee_id": self.referee.id,
                    "role": "head",
                }
            )
            self.env.cr.flush()

    def test_different_roles_allowed(self):
        """Test that different roles allowed."""
        ref2 = self.env["federation.referee"].create(
            {
                "name": "Assistant Ref",
            }
        )
        self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        assignment2 = self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": ref2.id,
                "role": "assistant_1",
            }
        )
        self.assertTrue(assignment2.id)

    def test_assignment_count_computed(self):
        """Test that assignment count computed."""
        self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        self.referee.invalidate_recordset()
        self.assertEqual(self.referee.assignment_count, 1)

    def test_confirmation_deadline_is_48_hours_before_match(self):
        """Test that confirmation deadline is 48 hours before match."""
        self.match.write({"date_scheduled": "2024-06-20 18:00:00"})
        assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )

        self.assertEqual(
            fields.Datetime.to_datetime(assignment.confirmation_deadline),
            fields.Datetime.to_datetime(self.match.date_scheduled)
            - timedelta(hours=48),
        )

    def test_overdue_assignment_is_flagged(self):
        """Test that overdue assignment is flagged."""
        self.match.write({"date_scheduled": "2024-01-05 12:00:00"})
        assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )

        self.assertTrue(assignment.is_confirmation_overdue)

    def test_confirm_rejects_expired_certification(self):
        """Test that confirm rejects expired certification."""
        expired_referee = self.env["federation.referee"].create(
            {
                "name": "Expired Referee",
                "certification_level": "national",
            }
        )
        self.env["federation.referee.certification"].create(
            {
                "name": "EXP-CERT",
                "referee_id": expired_referee.id,
                "level": "national",
                "issue_date": "2023-01-01",
                "expiry_date": "2024-01-01",
            }
        )
        self.match.write({"date_scheduled": "2024-06-20 18:00:00"})
        assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": expired_referee.id,
                "role": "head",
            }
        )

        with self.assertRaises(ValidationError):
            assignment.action_confirm()

    def test_match_readiness_detects_missing_head_referee(self):
        """Test that match readiness detects missing head referee."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Officiating Ready Rules",
                "code": "OFFREADY",
                "referee_required_count": 2,
            }
        )
        self.tournament.write({"rule_set_id": rule_set.id})
        assistant_referee = self.env["federation.referee"].create(
            {
                "name": "Assistant Only",
                "certification_level": "regional",
            }
        )
        assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": assistant_referee.id,
                "role": "assistant_1",
            }
        )
        assignment.action_confirm()

        self.assertFalse(self.match.is_officially_ready)
        self.assertIn("head referee", self.match.official_readiness_issues.lower())
        self.assertEqual(self.match.missing_referees_count, 1)

    def test_match_readiness_becomes_ready_with_required_confirmed_officials(self):
        """Test that match readiness becomes ready with required confirmed officials."""
        rule_set = self.env["federation.rule.set"].create(
            {
                "name": "Full Officiating Rules",
                "code": "FULLOFF",
                "referee_required_count": 2,
            }
        )
        self.tournament.write({"rule_set_id": rule_set.id})
        assistant_referee = self.env["federation.referee"].create(
            {
                "name": "Ready Assistant",
                "certification_level": "regional",
            }
        )
        head_assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        assistant_assignment = self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": assistant_referee.id,
                "role": "assistant_1",
            }
        )
        head_assignment.action_confirm()
        assistant_assignment.action_confirm()

        self.assertTrue(self.match.is_officially_ready)
        self.assertEqual(self.match.missing_referees_count, 0)

    # --- Certification date-boundary tests ---

    def _make_assignment(self, referee, role="head"):
        """Create a fresh match.referee assignment."""
        return self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": referee.id,
                "role": role,
            }
        )

    def test_cert_expiring_on_match_day_is_valid(self):
        """Cert whose expiry_date equals the match date is still valid (inclusive boundary)."""
        self.match.write({"date_scheduled": "2024-06-15 15:00:00"})
        ref = self.env["federation.referee"].create({"name": "Boundary Ref A"})
        self.env["federation.referee.certification"].create(
            {
                "name": "BOUNDARY-A",
                "referee_id": ref.id,
                "level": "national",
                "issue_date": "2024-01-01",
                "expiry_date": "2024-06-15",  # same day as match
            }
        )
        assignment = self._make_assignment(ref)
        # Should NOT raise — cert expires exactly on match day
        assignment.action_confirm()
        self.assertEqual(assignment.state, "confirmed")

    def test_cert_expired_day_before_match_is_rejected(self):
        """Cert expiring one day before the match is invalid."""
        self.match.write({"date_scheduled": "2024-06-15 15:00:00"})
        ref = self.env["federation.referee"].create({"name": "Boundary Ref B"})
        self.env["federation.referee.certification"].create(
            {
                "name": "BOUNDARY-B",
                "referee_id": ref.id,
                "level": "national",
                "issue_date": "2024-01-01",
                "expiry_date": "2024-06-14",  # day before match
            }
        )
        assignment = self._make_assignment(ref)
        with self.assertRaises(ValidationError):
            assignment.action_confirm()

    def test_cert_starting_on_match_day_is_valid(self):
        """Cert whose issue_date equals the match date is valid (inclusive boundary)."""
        self.match.write({"date_scheduled": "2024-06-15 15:00:00"})
        ref = self.env["federation.referee"].create({"name": "Boundary Ref C"})
        self.env["federation.referee.certification"].create(
            {
                "name": "BOUNDARY-C",
                "referee_id": ref.id,
                "level": "national",
                "issue_date": "2024-06-15",  # same day as match
                "expiry_date": "2025-06-15",
            }
        )
        assignment = self._make_assignment(ref)
        assignment.action_confirm()
        self.assertEqual(assignment.state, "confirmed")

    def test_cert_starting_after_match_is_invalid(self):
        """Cert whose issue_date is after the match date is invalid."""
        self.match.write({"date_scheduled": "2024-06-15 15:00:00"})
        ref = self.env["federation.referee"].create({"name": "Boundary Ref D"})
        self.env["federation.referee.certification"].create(
            {
                "name": "BOUNDARY-D",
                "referee_id": ref.id,
                "level": "national",
                "issue_date": "2024-06-16",  # one day after match
                "expiry_date": "2025-06-16",
            }
        )
        assignment = self._make_assignment(ref)
        with self.assertRaises(ValidationError):
            assignment.action_confirm()

    def test_no_cert_ids_falls_back_to_certification_level(self):
        """Referee with no cert records but a certification_level set can be confirmed."""
        self.match.write({"date_scheduled": "2024-06-15 15:00:00"})
        ref = self.env["federation.referee"].create(
            {
                "name": "Level-Only Ref",
                "certification_level": "regional",
            }
        )
        # No certification records — should fall back to certification_level check
        assignment = self._make_assignment(ref)
        assignment.action_confirm()
        self.assertEqual(assignment.state, "confirmed")

    def test_no_cert_ids_and_no_level_is_rejected(self):
        """Referee with no cert records AND no certification_level cannot be confirmed."""
        self.match.write({"date_scheduled": "2024-06-15 15:00:00"})
        ref = self.env["federation.referee"].create(
            {
                "name": "Uncertified Ref",
                "certification_level": False,
            }
        )
        assignment = self._make_assignment(ref)
        with self.assertRaises(ValidationError):
            assignment.action_confirm()

    def test_readiness_issues_include_cert_problem(self):
        """_get_readiness_issues returns the certification message when cert is expired."""
        self.match.write({"date_scheduled": "2024-06-15 15:00:00"})
        ref = self.env["federation.referee"].create({"name": "Readiness Check Ref"})
        self.env["federation.referee.certification"].create(
            {
                "name": "READINESS-CERT",
                "referee_id": ref.id,
                "level": "national",
                "issue_date": "2023-01-01",
                "expiry_date": "2023-12-31",  # expired before match
            }
        )
        assignment = self._make_assignment(ref)
        issues = assignment._get_readiness_issues()
        self.assertTrue(any("certification" in i.lower() for i in issues))
        self.assertFalse(assignment.assignment_ready)

    def test_availability_gap_creates_warning_without_blocking_confirmation(self):
        """Availability windows warn when uncovered but do not invalidate readiness on their own."""
        self.match.write({"date_scheduled": "2024-06-15 15:00:00"})
        self.env["federation.referee.availability"].create(
            {
                "referee_id": self.referee.id,
                "date_start": "2024-06-15 09:00:00",
                "date_end": "2024-06-15 10:00:00",
            }
        )

        assignment = self._make_assignment(self.referee)

        self.assertTrue(assignment.assignment_ready)
        self.assertTrue(assignment.assignment_has_warning)
        self.assertIn(
            "availability",
            (assignment.assignment_warning_feedback or "").lower(),
        )

    def test_overlapping_assignment_blocks_confirmation(self):
        """An overlapping assignment is allowed in draft but cannot be confirmed."""
        self.match.write({"date_scheduled": "2024-06-15 15:00:00"})
        other_match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team_b.id,
                "away_team_id": self.team_a.id,
                "date_scheduled": "2024-06-15 15:00:00",
                "state": "draft",
            }
        )
        self._make_assignment(self.referee).action_confirm()
        overlapping_assignment = self.env["federation.match.referee"].create(
            {
                "match_id": other_match.id,
                "referee_id": self.referee.id,
                "role": "assistant_1",
            }
        )

        self.assertFalse(overlapping_assignment.assignment_ready)
        self.assertIn(
            "overlapping",
            (overlapping_assignment.readiness_feedback or "").lower(),
        )
        with self.assertRaises(ValidationError):
            overlapping_assignment.action_confirm()


class TestCompetitionWorkspaceOfficiatingIntegration(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if cls.env.get("federation.competition.workspace.service") is None:
            raise unittest.SkipTest("Competition Workspace is not installed in this test run.")
        if cls.env.get("federation.venue") is None:
            raise unittest.SkipTest("Venue planning models are not installed in this test run.")

        cls.service = cls.env["federation.competition.workspace.service"]
        cls.club = cls.env["federation.club"].create({"name": "Workspace Ref Club"})
        cls.teams = cls.env["federation.team"]
        for index in range(1, 5):
            cls.teams |= cls.env["federation.team"].create(
                {
                    "name": f"Workspace Ref Team {index}",
                    "club_id": cls.club.id,
                }
            )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Workspace Ref Season",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        cls.competition_template = cls.env["federation.competition"].create(
            {"name": "Workspace Ref Competition", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Workspace Ref Edition",
                "competition_id": cls.competition_template.id,
                "season_id": cls.season.id,
                "date_start": "2024-06-01",
                "date_end": "2024-06-30",
            }
        )
        cls.venue = cls.env["federation.venue"].create({"name": "Ref Arena"})
        cls.court_1 = cls.env["federation.playing.area"].create(
            {"name": "Arena Court 1", "venue_id": cls.venue.id}
        )
        cls.court_2 = cls.env["federation.playing.area"].create(
            {"name": "Arena Court 2", "venue_id": cls.venue.id}
        )
        cls.division = cls.env["federation.tournament"].create(
            {
                "name": "Workspace Ref Division",
                "edition_id": cls.edition.id,
                "competition_id": cls.competition_template.id,
                "season_id": cls.season.id,
                "date_start": "2024-06-20",
                "date_end": "2024-06-20",
                "workspace_state": "planning",
            }
        )
        stage = cls.division._workspace_get_or_create_stage()
        cls.gameday = cls.env["federation.tournament.round"].create(
            {
                "name": "Ref Gameday",
                "stage_id": stage.id,
                "round_date": "2024-06-20",
            }
        )
        cls.slot_a = cls.env["federation.match.slot"].create(
            {
                "round_id": cls.gameday.id,
                "venue_id": cls.venue.id,
                "playing_area_id": cls.court_1.id,
                "start_datetime": "2024-06-20 15:00:00",
                "end_datetime": "2024-06-20 15:45:00",
            }
        )
        cls.slot_b = cls.env["federation.match.slot"].create(
            {
                "round_id": cls.gameday.id,
                "venue_id": cls.venue.id,
                "playing_area_id": cls.court_2.id,
                "start_datetime": "2024-06-20 15:00:00",
                "end_datetime": "2024-06-20 15:45:00",
            }
        )
        cls.match_a = cls.env["federation.match"].create(
            {
                "tournament_id": cls.division.id,
                "stage_id": stage.id,
                "home_team_id": cls.teams[0].id,
                "away_team_id": cls.teams[1].id,
                "state": "draft",
            }
        )
        cls.match_b = cls.env["federation.match"].create(
            {
                "tournament_id": cls.division.id,
                "stage_id": stage.id,
                "home_team_id": cls.teams[2].id,
                "away_team_id": cls.teams[3].id,
                "state": "draft",
            }
        )
        cls.referee = cls.env["federation.referee"].create(
            {
                "name": "Workspace Referee",
                "certification_level": "national",
            }
        )

    def test_workspace_validation_flags_referee_availability_gap(self):
        """Planner checks defer availability warnings until the gameday is published."""
        self.env["federation.referee.availability"].create(
            {
                "referee_id": self.referee.id,
                "date_start": "2024-06-20 08:00:00",
                "date_end": "2024-06-20 10:00:00",
            }
        )
        self.env["federation.match.referee"].create(
            {
                "match_id": self.match_a.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )

        validation = self.service.validate_match_assignment(self.match_a.id, self.slot_a.id)

        self.assertFalse(validation["blocking"])
        self.assertFalse(validation["warnings"])

        self.gameday._competition_workspace_transition_planner_state("published")
        published_validation = self.service.validate_match_assignment(
            self.match_a.id,
            self.slot_a.id,
        )

        self.assertEqual(
            [issue["code"] for issue in published_validation["warnings"]],
            ["referee_unavailable"],
        )

    def test_workspace_validation_blocks_double_booked_referee(self):
        """Planner validation blocks double-booked referees after planning is published."""
        self.env["federation.match.referee"].create(
            {
                "match_id": self.match_a.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        self.env["federation.match.referee"].create(
            {
                "match_id": self.match_b.id,
                "referee_id": self.referee.id,
                "role": "head",
            }
        )
        self.service.assign_match_to_slot(self.match_a.id, self.slot_a.id)

        draft_validation = self.service.validate_match_assignment(self.match_b.id, self.slot_b.id)
        self.assertFalse(draft_validation["blocking"])

        gameday_validation = self.service.validate_gameday(self.gameday.id)
        self.assertFalse(gameday_validation["blocking"])
        self.assertFalse(gameday_validation["warnings"])

        self.gameday._competition_workspace_transition_planner_state("published")

        published_gameday_validation = self.service.validate_gameday(self.gameday.id)
        self.assertIn(
            "officiating_not_ready",
            {issue["code"] for issue in published_gameday_validation["warnings"]},
        )

        validation = self.service.validate_match_assignment(self.match_b.id, self.slot_b.id)
        codes = {issue["code"] for issue in validation["blocking"]}

        self.assertIn("referee_double_booked", codes)
