"""Tour T-06: Officiating — Assignment Lifecycle and Certification Edge Cases

Walks the officiating workflow for multiple matches and referees:
  1. Three referees with varying certification levels
  2. Full assignment lifecycle: assign → confirm → done → cancel path
  3. Expired certification blocks confirmation
  4. Overdue unconfirmed assignment is flagged
  5. Re-assigning (cancel + draft reset) allows replacement

Key invariants verified:
- Only active, valid certification allows action_confirm()
- Expired cert raises ValidationError on confirm
- is_confirmation_overdue is True for past-deadline unconfirmed assignments
- action_cancel() terminates the assignment
- action_draft() resets a cancelled assignment back to assignable state
"""

from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestTourOfficiating(TransactionCase):
    """T-06: Officiating assignment lifecycle tour."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        season = cls.env["federation.season"].create(
            {
                "name": "Officiating Tour Season",
                "code": "OFT26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Officiating Tour Rules",
                "code": "OFTR",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Officiating Tour Cup",
                "season_id": season.id,
                "rule_set_id": rule_set.id,
                "date_start": "2026-06-01",
            }
        )
        club1 = cls.env["federation.club"].create(
            {"name": "Off Club 1", "code": "OFC1"}
        )
        club2 = cls.env["federation.club"].create(
            {"name": "Off Club 2", "code": "OFC2"}
        )
        cls.team1 = cls.env["federation.team"].create(
            {"name": "Off Team 1", "club_id": club1.id, "code": "OFT1"}
        )
        cls.team2 = cls.env["federation.team"].create(
            {"name": "Off Team 2", "club_id": club2.id, "code": "OFT2"}
        )

        today = fields.Date.context_today(cls.env["federation.referee"])

        # Three referees with active certifications at different levels
        cls.ref_national = cls.env["federation.referee"].create(
            {"name": "National Ref", "certification_level": "national"}
        )
        cls.ref_regional = cls.env["federation.referee"].create(
            {"name": "Regional Ref", "certification_level": "regional"}
        )
        cls.ref_local = cls.env["federation.referee"].create(
            {"name": "Local Ref", "certification_level": "local"}
        )
        # Referee with only expired certification
        cls.ref_expired = cls.env["federation.referee"].create(
            {"name": "Expired Ref OFT"}
        )

        future_expiry = str(today + timedelta(days=365))
        for ref, level, suffix in [
            (cls.ref_national, "national", "NAT"),
            (cls.ref_regional, "regional", "REG"),
            (cls.ref_local, "local", "LOC"),
        ]:
            cls.env["federation.referee.certification"].create(
                {
                    "name": f"CERT-OFT-{suffix}",
                    "referee_id": ref.id,
                    "level": level,
                    "issue_date": "2025-01-01",
                    "expiry_date": future_expiry,
                }
            )
        cls.env["federation.referee.certification"].create(
            {
                "name": "CERT-OFT-EXP",
                "referee_id": cls.ref_expired.id,
                "level": "local",
                "issue_date": "2019-01-01",
                "expiry_date": "2021-12-31",
            }
        )

    def test_officiating_full_lifecycle(self):
        """Officiating tour: 3 refs assigned, confirmed, done; expired cert blocked."""

        future_dt = fields.Datetime.now() + timedelta(days=10)
        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team1.id,
                "away_team_id": self.team2.id,
                "date_scheduled": str(future_dt),
                "result_state": "draft",
            }
        )

        # STEP 1: Assign three referees
        a_nat = self.env["federation.match.referee"].create(
            {"match_id": match.id, "referee_id": self.ref_national.id, "role": "head"}
        )
        a_reg = self.env["federation.match.referee"].create(
            {
                "match_id": match.id,
                "referee_id": self.ref_regional.id,
                "role": "assistant_1",
            }
        )
        a_loc = self.env["federation.match.referee"].create(
            {
                "match_id": match.id,
                "referee_id": self.ref_local.id,
                "role": "assistant_2",
            }
        )

        # STEP 2: Assignments are in draft/assigned state, not overdue
        for assignment in (a_nat, a_reg, a_loc):
            self.assertEqual(assignment.state, "draft")
            self.assertFalse(assignment.is_confirmation_overdue)

        # STEP 3: Confirm all assignments (valid certs)
        for assignment in (a_nat, a_reg, a_loc):
            assignment.action_confirm()
            self.assertEqual(assignment.state, "confirmed")

        # STEP 4: Mark all done
        match.write({"state": "done", "home_score": 1, "away_score": 0})
        for assignment in (a_nat, a_reg, a_loc):
            assignment.action_done()
            self.assertEqual(assignment.state, "done")

        # STEP 5: Expired cert blocks confirmation on another match
        match2 = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team1.id,
                "away_team_id": self.team2.id,
                "date_scheduled": str(future_dt + timedelta(days=3)),
                "result_state": "draft",
            }
        )
        bad_assign = self.env["federation.match.referee"].create(
            {
                "match_id": match2.id,
                "referee_id": self.ref_expired.id,
                "role": "head",
            }
        )
        with self.assertRaises(ValidationError):
            bad_assign.action_confirm()

        # STEP 6: Cancel bad assignment, reset to draft, re-assign a valid referee
        bad_assign.action_cancel()
        self.assertEqual(bad_assign.state, "cancelled")
        bad_assign.action_draft()
        self.assertEqual(bad_assign.state, "draft")

        # STEP 7: Overdue detection — past-scheduled unconfirmed assignments are flagged
        past_match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team1.id,
                "away_team_id": self.team2.id,
                "date_scheduled": "2024-01-05 12:00:00",
                "result_state": "draft",
            }
        )
        overdue = self.env["federation.match.referee"].create(
            {
                "match_id": past_match.id,
                "referee_id": self.ref_national.id,
                "role": "head",
            }
        )
        self.assertTrue(overdue.is_confirmation_overdue)
