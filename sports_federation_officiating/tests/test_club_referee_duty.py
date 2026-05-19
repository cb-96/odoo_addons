"""Tests for federation.match.club.referee.duty (Phase 5)."""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase


class TestClubRefereeDutyBase(TransactionCase):
    """Shared fixtures for club referee duty tests."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # Clubs and teams
        cls.club_a = cls.env["federation.club"].create({"name": "Club Alpha", "code": "CALP"})
        cls.club_b = cls.env["federation.club"].create({"name": "Club Beta", "code": "CBET"})

        cls.team_a = cls.env["federation.team"].create(
            {"name": "Team Alpha", "club_id": cls.club_a.id, "code": "TALP"}
        )
        cls.team_b = cls.env["federation.team"].create(
            {"name": "Team Beta", "club_id": cls.club_b.id, "code": "TBET"}
        )

        # Players belonging to club_a
        cls.player_a1 = cls.env["federation.player"].create(
            {
                "first_name": "Alice",
                "last_name": "Alpha",
                "club_id": cls.club_a.id,
                "birth_date": "1995-01-01",
            }
        )
        cls.player_a2 = cls.env["federation.player"].create(
            {
                "first_name": "Bob",
                "last_name": "Alpha",
                "club_id": cls.club_a.id,
                "birth_date": "1996-02-01",
            }
        )
        # Player belonging to club_b
        cls.player_b1 = cls.env["federation.player"].create(
            {
                "first_name": "Carlos",
                "last_name": "Beta",
                "club_id": cls.club_b.id,
                "birth_date": "1997-03-01",
            }
        )

        # Season / tournament / match
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Duty Season",
                "code": "DUTY24",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Duty Tournament",
                "code": "DTOUR",
                "season_id": cls.season.id,
                "date_start": "2024-06-01",
            }
        )
        future_date = fields.Datetime.now() + timedelta(days=10)
        cls.match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.team_a.id,
                "away_team_id": cls.team_b.id,
                "state": "draft",
                "date_scheduled": future_date,
            }
        )

    def _make_duty(self, club=None, role="table", state="draft"):
        """Helper: create a duty record."""
        club = club or self.club_a
        return self.env["federation.match.club.referee.duty"].create(
            {
                "match_id": self.match.id,
                "club_id": club.id,
                "role": role,
                "state": state,
            }
        )


class TestClubRefereeDutyLifecycle(TestClubRefereeDutyBase):
    """Duty lifecycle: draft → open → nominated → confirmed."""

    def test_create_duty_defaults_to_draft(self):
        """Newly created duty starts in draft state."""
        duty = self._make_duty()
        self.assertEqual(duty.state, "draft")

    def test_action_open_moves_to_open(self):
        """action_open transitions draft → open."""
        duty = self._make_duty()
        duty.action_open()
        self.assertEqual(duty.state, "open")

    def test_action_open_raises_if_not_draft(self):
        """action_open on a non-draft duty raises ValidationError."""
        duty = self._make_duty(state="open")
        with self.assertRaises(ValidationError):
            duty.action_open()

    def test_action_nominate_sets_player(self):
        """action_nominate on an open duty stores the player and moves to nominated."""
        duty = self._make_duty(state="open")
        duty.action_nominate(self.player_a1.id)
        self.assertEqual(duty.state, "nominated")
        self.assertEqual(duty.nominated_player_id, self.player_a1)
        self.assertTrue(duty.nominated_on)

    def test_action_nominate_raises_for_wrong_club_player(self):
        """action_nominate raises if player does not belong to duty's club."""
        duty = self._make_duty(club=self.club_a, state="open")
        with self.assertRaises(ValidationError):
            duty.action_nominate(self.player_b1.id)

    def test_action_nominate_raises_if_not_open_or_rejected(self):
        """action_nominate raises if duty is in draft or confirmed state."""
        duty_draft = self._make_duty(state="draft")
        with self.assertRaises(ValidationError):
            duty_draft.action_nominate(self.player_a1.id)

    def test_action_confirm_creates_assignment(self):
        """action_confirm creates a federation.match.referee record linked in assignment_id."""
        duty = self._make_duty(state="open")
        duty.action_nominate(self.player_a1.id)
        duty.action_confirm()
        self.assertEqual(duty.state, "confirmed")
        self.assertTrue(duty.assignment_id)
        assignment = duty.assignment_id
        self.assertEqual(assignment.match_id, self.match)
        self.assertEqual(assignment.role, duty.role)

    def test_action_confirm_raises_if_not_nominated(self):
        """action_confirm raises on open duty (no player nominated yet)."""
        duty = self._make_duty(state="open")
        with self.assertRaises(ValidationError):
            duty.action_confirm()

    def test_full_lifecycle_draft_to_confirmed(self):
        """Full happy path: draft → open → nominated → confirmed."""
        duty = self._make_duty()
        self.assertEqual(duty.state, "draft")
        duty.action_open()
        self.assertEqual(duty.state, "open")
        duty.action_nominate(self.player_a1.id)
        self.assertEqual(duty.state, "nominated")
        duty.action_confirm()
        self.assertEqual(duty.state, "confirmed")
        self.assertTrue(duty.assignment_id.exists())


class TestClubRefereeDutyRejectionPath(TestClubRefereeDutyBase):
    """Rejection path: nominated → rejected → re-nominated → confirmed."""

    def test_action_reject_moves_to_rejected(self):
        """action_reject transitions nominated → rejected."""
        duty = self._make_duty(state="open")
        duty.action_nominate(self.player_a1.id)
        duty.action_reject(reason="Insufficient experience")
        self.assertEqual(duty.state, "rejected")
        self.assertIn("Insufficient experience", duty.notes or "")

    def test_action_reject_raises_if_not_nominated(self):
        """action_reject raises on open duty."""
        duty = self._make_duty(state="open")
        with self.assertRaises(ValidationError):
            duty.action_reject()

    def test_renominate_after_rejection(self):
        """Club can re-nominate after rejection."""
        duty = self._make_duty(state="open")
        duty.action_nominate(self.player_a1.id)
        duty.action_reject(reason="Not eligible")
        # Re-nominate with second player
        duty.action_nominate(self.player_a2.id)
        self.assertEqual(duty.state, "nominated")
        self.assertEqual(duty.nominated_player_id, self.player_a2)

    def test_full_rejection_cycle_to_confirmed(self):
        """nominated → rejected → nominated → confirmed creates assignment."""
        duty = self._make_duty(state="open")
        duty.action_nominate(self.player_a1.id)
        duty.action_reject(reason="Try again")
        duty.action_nominate(self.player_a2.id)
        duty.action_confirm()
        self.assertEqual(duty.state, "confirmed")
        self.assertTrue(duty.assignment_id.exists())


class TestClubRefereeDutyCancelEscapeHatch(TestClubRefereeDutyBase):
    """action_cancel resets duty to draft from any non-confirmed state."""

    def test_cancel_from_open(self):
        duty = self._make_duty(state="open")
        duty.action_cancel()
        self.assertEqual(duty.state, "draft")

    def test_cancel_from_nominated(self):
        duty = self._make_duty(state="open")
        duty.action_nominate(self.player_a1.id)
        duty.action_cancel()
        self.assertEqual(duty.state, "draft")
        self.assertFalse(duty.nominated_player_id)

    def test_cancel_raises_on_confirmed(self):
        duty = self._make_duty(state="open")
        duty.action_nominate(self.player_a1.id)
        duty.action_confirm()
        with self.assertRaises(ValidationError):
            duty.action_cancel()


class TestClubRefereeDutyDeadline(TestClubRefereeDutyBase):
    """Nomination deadline computed fields."""

    def test_nomination_deadline_is_72h_before_match(self):
        """nomination_deadline is 72 h before match.date_scheduled."""
        duty = self._make_duty()
        self.assertTrue(duty.nomination_deadline)
        expected = fields.Datetime.to_datetime(self.match.date_scheduled) - timedelta(hours=72)
        self.assertEqual(duty.nomination_deadline, expected)

    def test_is_deadline_overdue_false_for_future_match(self):
        """is_deadline_overdue is False when match is well in the future."""
        duty = self._make_duty(state="open")
        # match is 10 days away, so deadline is 7 days away — not overdue
        self.assertFalse(duty.is_deadline_overdue)

    def test_is_deadline_overdue_true_for_past_match(self):
        """is_deadline_overdue becomes True when deadline has passed."""
        past_date = fields.Datetime.now() - timedelta(days=1)
        past_match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
                "state": "draft",
                "date_scheduled": past_date,
            }
        )
        duty = self.env["federation.match.club.referee.duty"].create(
            {
                "match_id": past_match.id,
                "club_id": self.club_a.id,
                "role": "table",
                "state": "open",
            }
        )
        self.assertTrue(duty.is_deadline_overdue)

    def test_is_deadline_overdue_false_when_confirmed(self):
        """is_deadline_overdue is False when duty is confirmed (even for past match)."""
        past_date = fields.Datetime.now() - timedelta(days=1)
        past_match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
                "state": "draft",
                "date_scheduled": past_date,
            }
        )
        duty = self.env["federation.match.club.referee.duty"].create(
            {
                "match_id": past_match.id,
                "club_id": self.club_a.id,
                "role": "table",
                "state": "open",
            }
        )
        duty.action_nominate(self.player_a1.id)
        duty.action_confirm()
        self.assertFalse(duty.is_deadline_overdue)


class TestClubRefereeDutyUniqueness(TestClubRefereeDutyBase):
    """SQL constraint: one duty per (match, club, role)."""

    def test_duplicate_duty_blocked(self):
        """Creating a second duty for same match/club/role raises."""
        self._make_duty(club=self.club_a, role="table")
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self._make_duty(club=self.club_a, role="table")


class TestClubRefereeDutyMatchExtension(TestClubRefereeDutyBase):
    """club_duty_pending_count on federation.match."""

    def test_pending_count_increments_on_open(self):
        """club_duty_pending_count counts non-confirmed duties."""
        initial = self.match.club_duty_pending_count
        self._make_duty(club=self.club_a, role="table")
        self.match.invalidate_recordset()
        self.assertEqual(self.match.club_duty_pending_count, initial + 1)

    def test_pending_count_decrements_on_confirm(self):
        """club_duty_pending_count decrements when duty confirmed."""
        duty = self._make_duty(state="open")
        duty.action_nominate(self.player_a1.id)
        self.match.invalidate_recordset()
        before = self.match.club_duty_pending_count
        duty.action_confirm()
        self.match.invalidate_recordset()
        after = self.match.club_duty_pending_count
        self.assertEqual(after, before - 1)
