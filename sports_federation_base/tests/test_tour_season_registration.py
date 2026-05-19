"""Tour T-05: Season Registration — Club Self-Service to Confirmation

Walks the complete season registration lifecycle:
  1. Create a season and open it
  2. Register a team (draft registration)
  3. Admin confirms the registration
  4. Cancel and restore to draft
  5. Re-confirm (idempotent close of season also exercised)

Key invariants verified:
- Season starts in 'draft', transitions to 'open' via action_open()
- Registration state: draft → confirmed → cancelled → draft → confirmed
- Duplicate team+season registration is rejected by DB constraint
- Season can be closed from 'open'
"""

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestTourSeasonRegistration(TransactionCase):
    """T-05: Season registration lifecycle tour."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.season = cls.env["federation.season"].create(
            {
                "name": "Registration Tour Season",
                "code": "REG26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.club = cls.env["federation.club"].create(
            {"name": "Registration Tour Club", "code": "REGC"}
        )
        cls.team = cls.env["federation.team"].create(
            {"name": "Registration Tour Team", "club_id": cls.club.id, "code": "REGT"}
        )
        cls.club2 = cls.env["federation.club"].create(
            {"name": "Second Tour Club", "code": "SEC2"}
        )
        cls.team2 = cls.env["federation.team"].create(
            {"name": "Second Tour Team", "club_id": cls.club2.id, "code": "SETT2"}
        )

    def test_season_registration_full_lifecycle(self):
        """Season registration: open season → register → confirm → cancel → re-confirm."""

        # STEP 1: Open the season
        self.assertEqual(self.season.state, "draft")
        self.season.action_open()
        self.assertEqual(self.season.state, "open")

        # STEP 2: Create a draft registration
        reg = self.env["federation.season.registration"].create(
            {
                "season_id": self.season.id,
                "team_id": self.team.id,
            }
        )
        self.assertEqual(reg.state, "draft")
        self.assertTrue(reg.name)
        self.assertNotEqual(reg.name, "New")

        # STEP 3: Confirm
        reg.action_confirm()
        self.assertEqual(reg.state, "confirmed")

        # STEP 4: Cancel
        reg.action_cancel()
        self.assertEqual(reg.state, "cancelled")

        # STEP 5: Return to draft
        reg.action_draft()
        self.assertEqual(reg.state, "draft")

        # STEP 6: Re-confirm
        reg.action_confirm()
        self.assertEqual(reg.state, "confirmed")

        # STEP 7: Duplicate registration (same team + season) is rejected
        with self.assertRaises(Exception):
            self.env["federation.season.registration"].create(
                {
                    "season_id": self.season.id,
                    "team_id": self.team.id,
                }
            )

        # STEP 8: Register second team and close the season
        reg2 = self.env["federation.season.registration"].create(
            {
                "season_id": self.season.id,
                "team_id": self.team2.id,
            }
        )
        reg2.action_confirm()

        self.season.action_close()
        self.assertEqual(self.season.state, "closed")
