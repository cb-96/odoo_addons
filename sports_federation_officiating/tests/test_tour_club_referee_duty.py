"""Tour T-13b: Club Referee Duty — Full Nomination Lifecycle

Walks the club referee duty workflow end-to-end:
  1. Planner creates duty (draft)
  2. action_open notifies club (draft → open)
  3. Club nominates a player (open → nominated)
  4. Federation admin confirms; federation.match.referee created (confirmed)
  5. Rejection path: nominated → rejected → re-nominated → confirmed
  6. Deadline computed as 72h before match; overdue flag verified
  7. SQL uniqueness: duplicate (match, club, role) blocked
  8. Cross-club nomination blocked (player from different club)
  9. cancel escape hatch resets to draft; blocked on confirmed
  10. match.club_duty_pending_count reflects open duties only

Key invariants:
- assignment_id populated and linked to federation.match.referee on confirm
- nominated_player_id cleared on cancel
- is_deadline_overdue True when deadline < now and state != confirmed
- unique constraint raises on second (match, club, role)
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestTourClubRefereeDuty(TransactionCase):
    """Tour T-13b: Club referee duty nomination lifecycle."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.season = cls.env["federation.season"].create(
            {
                "name": "Duty Tour Season",
                "code": "DTS26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        rule_set = cls.env["federation.rule.set"].create(
            {"name": "Duty Rules", "code": "DR", "points_win": 3, "points_draw": 1, "points_loss": 0}
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Duty Tour Cup",
                "code": "DTC26",
                "season_id": cls.season.id,
                "rule_set_id": rule_set.id,
                "date_start": "2026-06-01",
            }
        )

        cls.club_a = cls.env["federation.club"].create({"name": "Alpha FC", "code": "AFC"})
        cls.club_b = cls.env["federation.club"].create({"name": "Beta FC", "code": "BFC"})
        cls.team_a = cls.env["federation.team"].create({"name": "Alpha Team", "club_id": cls.club_a.id, "code": "ATA"})
        cls.team_b = cls.env["federation.team"].create({"name": "Beta Team", "club_id": cls.club_b.id, "code": "ATB"})

        cls.player_a1 = cls.env["federation.player"].create(
            {"first_name": "Alice", "last_name": "Alpha", "club_id": cls.club_a.id, "birth_date": "1998-03-01"}
        )
        cls.player_a2 = cls.env["federation.player"].create(
            {"first_name": "Anna", "last_name": "Alpha", "club_id": cls.club_a.id, "birth_date": "1999-05-01"}
        )
        cls.player_b1 = cls.env["federation.player"].create(
            {"first_name": "Boris", "last_name": "Beta", "club_id": cls.club_b.id, "birth_date": "1997-07-01"}
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

    def _duty(self, club=None, role="table", state="draft"):
        return self.env["federation.match.club.referee.duty"].create(
            {
                "match_id": self.match.id,
                "club_id": (club or self.club_a).id,
                "role": role,
                "state": state,
            }
        )

    def test_full_happy_path(self):
        """draft → open → nominated → confirmed creates assignment."""
        duty = self._duty()
        self.assertEqual(duty.state, "draft")

        duty.action_open()
        self.assertEqual(duty.state, "open")

        duty.action_nominate(self.player_a1.id)
        self.assertEqual(duty.state, "nominated")
        self.assertEqual(duty.nominated_player_id, self.player_a1)
        self.assertTrue(duty.nominated_on)

        duty.action_confirm()
        self.assertEqual(duty.state, "confirmed")
        self.assertTrue(duty.assignment_id.exists())
        self.assertEqual(duty.assignment_id.match_id, self.match)
        self.assertEqual(duty.assignment_id.role, duty.role)

    def test_rejection_and_renomination_cycle(self):
        """nominated → rejected → re-nominated → confirmed."""
        duty = self._duty(state="open")
        duty.action_nominate(self.player_a1.id)
        duty.action_reject(reason="Not available")
        self.assertEqual(duty.state, "rejected")
        self.assertIn("Not available", duty.notes or "")

        duty.action_nominate(self.player_a2.id)
        self.assertEqual(duty.state, "nominated")
        self.assertEqual(duty.nominated_player_id, self.player_a2)

        duty.action_confirm()
        self.assertEqual(duty.state, "confirmed")

    def test_cross_club_nomination_blocked(self):
        """Nominating a player from the wrong club raises ValidationError."""
        duty = self._duty(club=self.club_a, state="open")
        with self.assertRaises(ValidationError):
            duty.action_nominate(self.player_b1.id)

    def test_cancel_resets_to_draft(self):
        """action_cancel resets nominated duty back to draft, clears nominee."""
        duty = self._duty(state="open")
        duty.action_nominate(self.player_a1.id)
        self.assertEqual(duty.state, "nominated")

        duty.action_cancel()
        self.assertEqual(duty.state, "draft")
        self.assertFalse(duty.nominated_player_id)

    def test_cancel_blocked_on_confirmed(self):
        """action_cancel raises on a confirmed duty."""
        duty = self._duty(state="open")
        duty.action_nominate(self.player_a1.id)
        duty.action_confirm()
        with self.assertRaises(ValidationError):
            duty.action_cancel()

    def test_nomination_deadline_72h_before_match(self):
        """nomination_deadline = match.date_scheduled − 72h."""
        duty = self._duty()
        self.assertTrue(duty.nomination_deadline)
        expected = fields.Datetime.to_datetime(self.match.date_scheduled) - timedelta(hours=72)
        self.assertEqual(duty.nomination_deadline, expected)

    def test_deadline_overdue_flag_past_match(self):
        """is_deadline_overdue is True when match is in the past and duty not confirmed."""
        past = fields.Datetime.now() - timedelta(days=2)
        past_match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
                "state": "draft",
                "date_scheduled": past,
            }
        )
        duty = self.env["federation.match.club.referee.duty"].create(
            {
                "match_id": past_match.id,
                "club_id": self.club_a.id,
                "role": "assistant_1",
                "state": "open",
            }
        )
        self.assertTrue(duty.is_deadline_overdue)

    def test_deadline_overdue_false_when_confirmed(self):
        """is_deadline_overdue is False after confirmation regardless of deadline."""
        past = fields.Datetime.now() - timedelta(days=2)
        past_match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
                "state": "draft",
                "date_scheduled": past,
            }
        )
        duty = self.env["federation.match.club.referee.duty"].create(
            {
                "match_id": past_match.id,
                "club_id": self.club_a.id,
                "role": "fourth",
                "state": "open",
            }
        )
        duty.action_nominate(self.player_a1.id)
        duty.action_confirm()
        self.assertFalse(duty.is_deadline_overdue)

    def test_duplicate_duty_blocked(self):
        """SQL unique constraint prevents two duties for same match/club/role."""
        self._duty(role="table")
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self._duty(role="table")

    def test_pending_count_on_match(self):
        """club_duty_pending_count increments on open duty and decrements on confirm."""
        initial = self.match.club_duty_pending_count
        duty = self._duty(role="fourth", state="open")
        self.match.invalidate_recordset()
        self.assertEqual(self.match.club_duty_pending_count, initial + 1)

        duty.action_nominate(self.player_a1.id)
        duty.action_confirm()
        self.match.invalidate_recordset()
        self.assertEqual(self.match.club_duty_pending_count, initial)

    def test_display_name_is_readable(self):
        """display_name contains match, club, and role information."""
        duty = self._duty(role="table")
        self.assertIn(self.club_a.name, duty.display_name)
