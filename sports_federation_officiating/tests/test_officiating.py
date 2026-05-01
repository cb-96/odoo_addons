"""Tests for sports_federation_officiating: referees, certifications, match assignments."""

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
