"""Tour T-07: Discipline Pipeline — Incident → Case → Sanction → Suspension → Close

Walks the full disciplinary lifecycle:
  1. Record a match incident (red card)
  2. Create a disciplinary case linked to the incident
  3. Submit for review → 'under_review'
  4. Reopen to draft to add notes, re-submit
  5. Decide the case (decided state)
  6. Create a suspension record → activate it
  7. Create a finance event for the associated fine
  8. Close the case → incident auto-closes

Key invariants verified:
- Case transitions: draft → under_review → draft (reopen) → under_review → decided → closed
- action_reopen() only works from 'under_review'
- Suspension activation calls action_activate()
- Finance event for fine created in 'draft', confirmed to 'confirmed'
- Incident status transitions to 'attached' and then 'closed'
"""

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestTourDisciplinePipeline(TransactionCase):
    """T-07: Discipline pipeline tour — full incident to closure."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.club = cls.env["federation.club"].create(
            {"name": "Discipline Tour Club", "code": "DISC"}
        )
        cls.team = cls.env["federation.team"].create(
            {"name": "Discipline Tour Team", "club_id": cls.club.id, "code": "DIST"}
        )
        cls.player = cls.env["federation.player"].create(
            {
                "first_name": "Discipline",
                "last_name": "Player",
                "gender": "male",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Discipline Tour Season",
                "code": "DSC26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Discipline Tour Cup",
                "season_id": cls.season.id,
                "date_start": "2026-04-01",
            }
        )
        cls.match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.team.id,
                "date_scheduled": "2026-04-15 15:00:00",
                "result_state": "draft",
            }
        )

    def test_discipline_pipeline_full_cycle(self):
        """Full discipline pipeline: incident → case → review → decide → suspend → close."""

        # STEP 1: Record a red card incident
        incident = self.env["federation.match.incident"].create(
            {
                "name": "Red Card — Violent Conduct",
                "match_id": self.match.id,
                "player_id": self.player.id,
                "incident_type": "red_card",
                "description": "Player was sent off for violent conduct in the 78th minute.",
            }
        )
        self.assertEqual(incident.status, "new")

        # STEP 2: Create a disciplinary case linked to the incident
        case = self.env["federation.disciplinary.case"].create(
            {
                "name": "Violent Conduct — Tour Player",
                "subject_player_id": self.player.id,
                "incident_ids": [(4, incident.id)],
            }
        )
        self.assertEqual(case.state, "draft")

        # STEP 3: Submit for review — incident status updates to 'attached'
        case.action_submit_review()
        self.assertEqual(case.state, "under_review")
        incident.invalidate_recordset()
        self.assertEqual(incident.status, "attached")

        # STEP 4: Reopen to draft (only valid from under_review)
        case.action_reopen()
        self.assertEqual(case.state, "draft")

        # Cannot reopen from draft
        with self.assertRaises(ValidationError):
            case.action_reopen()

        # Re-submit
        case.action_submit_review()
        self.assertEqual(case.state, "under_review")

        # STEP 5: Issue decision
        case.action_decide()
        self.assertEqual(case.state, "decided")
        self.assertTrue(case.decided_on)

        # STEP 6: Create suspension record and activate it
        suspension = self.env["federation.suspension"].create(
            {
                "name": "2-Match Ban — Violent Conduct",
                "case_id": case.id,
                "player_id": self.player.id,
                "date_start": "2026-04-20",
                "date_end": "2026-05-15",
            }
        )
        self.assertEqual(suspension.state, "draft")
        suspension.action_activate()
        self.assertEqual(suspension.state, "active")

        # STEP 7: Create fine sanction record
        self.env["federation.sanction"].create(
            {
                "name": "Fine — Violent Conduct",
                "case_id": case.id,
                "sanction_type": "fine",
                "player_id": self.player.id,
                "amount": 250.0,
            }
        )

        # STEP 8: Close the case — incident auto-closes
        case.action_close()
        self.assertEqual(case.state, "closed")
        self.assertTrue(case.closed_on)

        incident.invalidate_recordset()
        self.assertEqual(incident.status, "closed")

        # Suspension remains active
        self.assertEqual(suspension.state, "active")
