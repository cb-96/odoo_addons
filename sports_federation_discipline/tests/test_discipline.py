from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestDiscipline(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Test Club",
                "code": "TEST",
            }
        )
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Test Team",
                "club_id": cls.club.id,
                "code": "TT",
            }
        )
        cls.player = cls.env["federation.player"].create(
            {
                "name": "Test Player",
                "first_name": "Test",
                "last_name": "Player",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Test Season",
                "code": "TS2024",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Test Tournament",
                "code": "TTOUR",
                "season_id": cls.season.id,
                "date_start": "2024-06-01",
            }
        )
        cls.match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.tournament.id,
                "home_team_id": cls.team.id,
                "date_scheduled": "2024-06-15 15:00:00",
            }
        )

    def test_create_incident_with_subject(self):
        """Test creating an incident with a valid subject."""
        incident = self.env["federation.match.incident"].create(
            {
                "name": "Yellow Card Incident",
                "match_id": self.match.id,
                "player_id": self.player.id,
                "incident_type": "yellow_card",
                "description": "Player received a yellow card for foul play.",
            }
        )
        self.assertTrue(incident.id)
        self.assertEqual(incident.status, "new")
        self.assertEqual(incident.player_id, self.player)

    def test_incident_requires_subject_reference(self):
        """Test that incident requires at least one subject reference.

        @api.constrains only fires when a constrained field is set, so we
        must explicitly set one field to False to trigger the check.
        """
        with self.assertRaises(ValidationError):
            self.env["federation.match.incident"].create(
                {
                    "name": "Bad Incident",
                    "incident_type": "other",
                    "description": "No subject reference provided.",
                    "player_id": False,
                }
            )

    def test_create_case_and_attach_incident(self):
        """Test creating a case and attaching an incident."""
        incident = self.env["federation.match.incident"].create(
            {
                "name": "Test Incident",
                "match_id": self.match.id,
                "player_id": self.player.id,
                "incident_type": "misconduct",
                "description": "Player misconduct during match.",
            }
        )
        case = self.env["federation.disciplinary.case"].create(
            {
                "name": "Test Case",
                "subject_player_id": self.player.id,
                "summary": "Case for player misconduct.",
                "incident_ids": [(4, incident.id)],
            }
        )
        self.assertTrue(case.id)
        self.assertEqual(case.state, "draft")
        self.assertIn(incident, case.incident_ids)

    def test_case_related_fields_use_distinct_labels(self):
        """Count fields should not reuse the relation labels that Odoo warns on."""
        case_model = self.env["federation.disciplinary.case"]
        self.assertEqual(case_model._fields["incident_ids"].string, "Incidents")
        self.assertEqual(case_model._fields["incident_count"].string, "Incident Count")
        self.assertEqual(case_model._fields["sanction_ids"].string, "Sanctions")
        self.assertEqual(case_model._fields["sanction_count"].string, "Sanction Count")
        self.assertEqual(case_model._fields["suspension_ids"].string, "Suspensions")
        self.assertEqual(
            case_model._fields["suspension_count"].string, "Suspension Count"
        )

        case = case_model.create(
            {
                "name": "Case Labels",
                "subject_player_id": self.player.id,
                "summary": "Verify related counters.",
            }
        )
        self.assertEqual(case.incident_count, 0)
        self.assertEqual(case.sanction_count, 0)
        self.assertEqual(case.suspension_count, 0)

    def test_case_state_transitions(self):
        """Test case state transitions."""
        case = self.env["federation.disciplinary.case"].create(
            {
                "name": "Test Case",
                "subject_player_id": self.player.id,
                "summary": "Test case for state transitions.",
            }
        )
        self.assertEqual(case.state, "draft")

        case.action_submit_review()
        self.assertEqual(case.state, "under_review")

        case.action_decide()
        self.assertEqual(case.state, "decided")
        self.assertTrue(case.decided_on)

        case.action_mark_appealed()
        self.assertEqual(case.state, "appealed")

        case.action_close()
        self.assertEqual(case.state, "closed")
        self.assertTrue(case.closed_on)

    def test_review_submission_and_reopen_enforce_state_guards(self):
        """Test review submission and reopen only allow the documented states."""
        case = self.env["federation.disciplinary.case"].create(
            {
                "name": "Review Guard Case",
                "subject_player_id": self.player.id,
                "summary": "Exercise review workflow guards.",
            }
        )

        with self.assertRaises(ValidationError):
            case.action_reopen()
        self.assertEqual(case.state, "draft")

        case.action_submit_review()
        self.assertEqual(case.state, "under_review")

        with self.assertRaises(ValidationError):
            case.action_submit_review()

        case.action_reopen()
        self.assertEqual(case.state, "draft")

    def test_create_sanction(self):
        """Test creating a sanction."""
        case = self.env["federation.disciplinary.case"].create(
            {
                "name": "Test Case",
                "subject_player_id": self.player.id,
                "summary": "Test case for sanction.",
            }
        )
        sanction = self.env["federation.sanction"].create(
            {
                "name": "Fine for Misconduct",
                "case_id": case.id,
                "sanction_type": "fine",
                "player_id": self.player.id,
                "amount": 500.00,
                "effective_date": "2024-07-01",
            }
        )
        self.assertTrue(sanction.id)
        self.assertEqual(sanction.sanction_type, "fine")
        self.assertEqual(sanction.amount, 500.00)

    def test_create_suspension(self):
        """Test creating a suspension."""
        case = self.env["federation.disciplinary.case"].create(
            {
                "name": "Test Case",
                "subject_player_id": self.player.id,
                "summary": "Test case for suspension.",
            }
        )
        suspension = self.env["federation.suspension"].create(
            {
                "name": "3-Match Suspension",
                "case_id": case.id,
                "player_id": self.player.id,
                "date_start": "2024-07-01",
                "date_end": "2024-07-31",
            }
        )
        self.assertTrue(suspension.id)
        self.assertEqual(suspension.state, "draft")

        suspension.action_activate()
        self.assertEqual(suspension.state, "active")

    def test_suspension_date_validation(self):
        """Test that suspension end date must be >= start date."""
        case = self.env["federation.disciplinary.case"].create(
            {
                "name": "Test Case",
                "subject_player_id": self.player.id,
                "summary": "Test case for suspension validation.",
            }
        )
        with self.assertRaises(ValidationError):
            self.env["federation.suspension"].create(
                {
                    "name": "Bad Suspension",
                    "case_id": case.id,
                    "player_id": self.player.id,
                    "date_start": "2024-07-31",
                    "date_end": "2024-07-01",
                }
            )

    # ------------------------------------------------------------------
    # Suspension activation / expiry / eligibility-gate edge cases
    # ------------------------------------------------------------------

    def _make_case(self, suffix=""):
        return self.env["federation.disciplinary.case"].create(
            {
                "name": f"Case {suffix}",
                "subject_player_id": self.player.id,
                "summary": "Edge-case test case.",
            }
        )

    def _make_suspension(
        self, case, name="Suspension", start="2024-07-01", end="2024-07-31"
    ):
        return self.env["federation.suspension"].create(
            {
                "name": name,
                "case_id": case.id,
                "player_id": self.player.id,
                "date_start": start,
                "date_end": end,
            }
        )

    def test_suspension_activation_sets_player_suspended(self):
        """Activating a suspension must flip the player state to 'suspended'."""
        case = self._make_case("activate")
        suspension = self._make_suspension(case)
        self.assertEqual(self.player.state, "active")

        suspension.action_activate()

        self.assertEqual(suspension.state, "active")
        self.assertEqual(self.player.state, "suspended")

    def test_suspension_already_active_is_noop(self):
        """Calling action_activate() on an already-active suspension is a no-op."""
        case = self._make_case("noop")
        suspension = self._make_suspension(case)
        suspension.action_activate()
        self.assertEqual(suspension.state, "active")

        # Second call must not raise and must leave state unchanged.
        suspension.action_activate()
        self.assertEqual(suspension.state, "active")
        self.assertEqual(self.player.state, "suspended")

    def test_suspension_cancel_from_draft_restores_player(self):
        """Cancelling a draft suspension leaves the player state unchanged (already active)."""
        case = self._make_case("cancel-draft")
        suspension = self._make_suspension(case)
        # Player is active; suspension in draft; cancel it.
        suspension.action_cancel()
        self.assertEqual(suspension.state, "cancelled")
        # Player had no active suspensions, so state stays active.
        self.assertEqual(self.player.state, "active")

    def test_suspension_cancel_from_active_restores_player(self):
        """Cancelling the only active suspension restores the player to active."""
        case = self._make_case("cancel-active")
        suspension = self._make_suspension(case)
        suspension.action_activate()
        self.assertEqual(self.player.state, "suspended")

        suspension.action_cancel()
        self.assertEqual(suspension.state, "cancelled")
        self.assertEqual(self.player.state, "active")

    def test_suspension_cancel_with_another_active_keeps_player_suspended(self):
        """Cancelling one suspension keeps the player suspended if another is still active."""
        case1 = self._make_case("multi-1")
        case2 = self._make_case("multi-2")
        s1 = self._make_suspension(
            case1, name="S1", start="2024-07-01", end="2024-07-15"
        )
        s2 = self._make_suspension(
            case2, name="S2", start="2024-07-16", end="2024-07-31"
        )
        s1.action_activate()
        s2.action_activate()
        self.assertEqual(self.player.state, "suspended")

        # Cancel first suspension; second is still active.
        s1.action_cancel()
        self.assertEqual(self.player.state, "suspended")

    def test_suspension_expire_restores_player_when_no_other_active(self):
        """Expiring the only active suspension restores the player state."""
        case = self._make_case("expire")
        suspension = self._make_suspension(case)
        suspension.action_activate()
        self.assertEqual(self.player.state, "suspended")

        suspension.action_expire()
        self.assertEqual(suspension.state, "expired")
        self.assertEqual(self.player.state, "active")

    def test_suspension_expire_draft_is_noop(self):
        """Calling action_expire() on a draft suspension does nothing (only active expire)."""
        case = self._make_case("expire-draft")
        suspension = self._make_suspension(case)
        self.assertEqual(suspension.state, "draft")

        suspension.action_expire()
        self.assertEqual(suspension.state, "draft")

    def test_suspension_activate_skips_dispatcher_when_absent(self):
        """action_activate() must not raise when the notification dispatcher is not installed."""
        case = self._make_case("no-dispatcher")
        suspension = self._make_suspension(case)
        # Ensure dispatcher is genuinely absent in the test environment.
        self.assertIsNone(self.env.get("federation.notification.dispatcher"))
        # Must complete without error.
        suspension.action_activate()
        self.assertEqual(suspension.state, "active")

    def test_player_suspension_count_reflects_linked_suspensions(self):
        """federation.player.suspension_count must include all suspensions for the player."""
        case = self._make_case("count")
        self._make_suspension(case, name="S-A", start="2024-07-01", end="2024-07-10")
        self._make_suspension(case, name="S-B", start="2024-07-11", end="2024-07-20")
        self.player.invalidate_recordset()
        self.assertEqual(self.player.suspension_count, 2)
