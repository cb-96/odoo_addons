"""Tour T-03: Match Day Operations — Referee Assignment Lifecycle

Walks the full match-day referee workflow for a single match:
  1. Create referee with active certification
  2. Create a scheduled match
  3. Assign head referee, two assistants
  4. Confirm each assignment
  5. Complete the match, mark all assignments done
  6. Verify that an expired certification blocks confirmation

Key invariants verified:
- Active certification allows confirmation
- Expired certification blocks action_confirm() with ValidationError
- Assignments reach 'done' state after match completion
- Overdue assignments (past confirmation deadline) are flagged
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestTourMatchDay(TransactionCase):
    """T-03: Match day referee assignment tour."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        season = cls.env["federation.season"].create(
            {
                "name": "Match Day Tour Season",
                "code": "MDT26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Match Day Tour Rules",
                "code": "MDTR",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )
        tournament = cls.env["federation.tournament"].create(
            {
                "name": "Match Day Tour Cup",
                "season_id": season.id,
                "rule_set_id": rule_set.id,
                "date_start": "2026-06-01",
            }
        )
        club_h = cls.env["federation.club"].create(
            {"name": "Match Day Home Club", "code": "MDHC"}
        )
        club_a = cls.env["federation.club"].create(
            {"name": "Match Day Away Club", "code": "MDAC"}
        )
        cls.team_h = cls.env["federation.team"].create(
            {"name": "Match Day Home", "club_id": club_h.id, "code": "MDTH"}
        )
        cls.team_a = cls.env["federation.team"].create(
            {"name": "Match Day Away", "club_id": club_a.id, "code": "MDTA"}
        )
        cls.tournament = tournament

        # Referees
        cls.head_ref = cls.env["federation.referee"].create(
            {"name": "Head Referee MD", "certification_level": "national"}
        )
        cls.asst1 = cls.env["federation.referee"].create(
            {"name": "Assistant 1 MD", "certification_level": "regional"}
        )
        cls.asst2 = cls.env["federation.referee"].create(
            {"name": "Assistant 2 MD", "certification_level": "regional"}
        )
        cls.expired_ref = cls.env["federation.referee"].create(
            {"name": "Expired Ref MD"}
        )

        today = fields.Date.context_today(cls.env["federation.referee"])

        # Active certification for head referee
        cls.env["federation.referee.certification"].create(
            {
                "name": "CERT-HEAD-MD",
                "referee_id": cls.head_ref.id,
                "level": "national",
                "issue_date": "2025-01-01",
                "expiry_date": str(today + timedelta(days=365)),
            }
        )
        # Active certs for assistants
        for ref, suffix in [(cls.asst1, "A1"), (cls.asst2, "A2")]:
            cls.env["federation.referee.certification"].create(
                {
                    "name": f"CERT-{suffix}-MD",
                    "referee_id": ref.id,
                    "level": "regional",
                    "issue_date": "2025-01-01",
                    "expiry_date": str(today + timedelta(days=365)),
                }
            )
        # Expired certification
        cls.env["federation.referee.certification"].create(
            {
                "name": "CERT-EXP-MD",
                "referee_id": cls.expired_ref.id,
                "level": "local",
                "issue_date": "2020-01-01",
                "expiry_date": "2022-12-31",
            }
        )

    def test_match_day_referee_assignment_lifecycle(self):
        """Full match-day referee assignment: assign → confirm × 3 → done × 3."""

        # STEP 1: Create a scheduled match (in the future so deadline is not overdue)
        future_date = fields.Datetime.now() + timedelta(days=10)
        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team_h.id,
                "away_team_id": self.team_a.id,
                "date_scheduled": str(future_date),
                "result_state": "draft",
            }
        )

        # STEP 2: Assign head referee + 2 assistants
        assign_head = self.env["federation.match.referee"].create(
            {
                "match_id": match.id,
                "referee_id": self.head_ref.id,
                "role": "head",
            }
        )
        assign_a1 = self.env["federation.match.referee"].create(
            {
                "match_id": match.id,
                "referee_id": self.asst1.id,
                "role": "assistant_1",
            }
        )
        assign_a2 = self.env["federation.match.referee"].create(
            {
                "match_id": match.id,
                "referee_id": self.asst2.id,
                "role": "assistant_2",
            }
        )
        self.assertEqual(assign_head.state, "draft")
        self.assertFalse(assign_head.is_confirmation_overdue)

        # STEP 3: Confirm each assignment
        for assignment in (assign_head, assign_a1, assign_a2):
            assignment.action_confirm()
            self.assertEqual(assignment.state, "confirmed")
            self.assertTrue(assignment.confirmed_on)

        # STEP 4: Complete the match, mark all assignments done
        match.write({"state": "done", "home_score": 2, "away_score": 0})
        for assignment in (assign_head, assign_a1, assign_a2):
            assignment.action_done()
            self.assertEqual(assignment.state, "done")
            self.assertTrue(assignment.completed_on)

        # STEP 5: Expired certification blocks confirmation on a different match
        match2 = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team_h.id,
                "away_team_id": self.team_a.id,
                "date_scheduled": str(future_date + timedelta(days=1)),
                "result_state": "draft",
            }
        )
        expired_assignment = self.env["federation.match.referee"].create(
            {
                "match_id": match2.id,
                "referee_id": self.expired_ref.id,
                "role": "head",
            }
        )
        with self.assertRaises(ValidationError):
            expired_assignment.action_confirm()

        # STEP 6: Overdue flag is set for past-scheduled unconfirmed assignments
        past_date = "2024-01-05 12:00:00"
        match3 = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team_h.id,
                "away_team_id": self.team_a.id,
                "date_scheduled": past_date,
                "result_state": "draft",
            }
        )
        overdue_assign = self.env["federation.match.referee"].create(
            {
                "match_id": match3.id,
                "referee_id": self.head_ref.id,
                "role": "head",
            }
        )
        self.assertTrue(overdue_assign.is_confirmation_overdue)
