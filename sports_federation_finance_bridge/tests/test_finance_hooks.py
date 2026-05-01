"""
Tests for Phase 2 finance hooks:
- action_create_venue_finance_event works correctly on a match with a venue
- On result approval, if result_fee_type_id is set, a finance event is created
- Multiple matches can each have their own auto finance event on approval
- Without result_fee_type_id, no extra event is created on approval
"""

from odoo.tests import TransactionCase
from odoo.exceptions import ValidationError


class TestFinanceHooks(TransactionCase):
    """Finance hook integration tests requiring result_control module."""

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.has_result_control = "result_state" in cls.env["federation.match"]._fields

        cls.club = cls.env["federation.club"].create(
            {
                "name": "Hook Test Club",
                "code": "HTC",
            }
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "Hook Team A",
                "club_id": cls.club.id,
                "code": "HTA",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "Hook Team B",
                "club_id": cls.club.id,
                "code": "HTB",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Hook Season",
                "code": "HS2024",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Hook Tournament",
                "code": "HTOUR",
                "season_id": cls.season.id,
                "date_start": "2024-06-01",
            }
        )
        cls.venue = cls.env["federation.venue"].create(
            {
                "name": "Hook Venue",
                "city": "Hook City",
            }
        )
        cls.fee_type_venue = cls.env["federation.fee.type"].create(
            {
                "name": "Venue Booking",
                "code": "venue_booking",
                "category": "other",
                "default_amount": 150.00,
            }
        )
        cls.fee_type_result = cls.env["federation.fee.type"].create(
            {
                "name": "Result Processing",
                "code": "RESULT_PROC",
                "category": "other",
                "default_amount": 25.00,
            }
        )
        cls.manager_group = cls.env.ref(
            "sports_federation_base.group_federation_manager"
        )
        cls.validator_group = cls.env.ref(
            "sports_federation_result_control.group_result_validator"
        )
        cls.approver_group = cls.env.ref(
            "sports_federation_result_control.group_result_approver"
        )
        cls.validator_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Finance Hook Validator",
                    "login": "finance.hook.validator@example.com",
                    "email": "finance.hook.validator@example.com",
                    "group_ids": [
                        (6, 0, [cls.manager_group.id, cls.validator_group.id])
                    ],
                }
            )
        )
        cls.approver_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Finance Hook Approver",
                    "login": "finance.hook.approver@example.com",
                    "email": "finance.hook.approver@example.com",
                    "group_ids": [
                        (6, 0, [cls.manager_group.id, cls.approver_group.id])
                    ],
                }
            )
        )

    def _create_done_match(self, with_venue=True, with_result_fee=False):
        """Helper to create a done match with optional configuration."""
        vals = {
            "tournament_id": self.tournament.id,
            "home_team_id": self.team_a.id,
            "away_team_id": self.team_b.id,
            "home_score": 2,
            "away_score": 1,
            "state": "done",
        }
        if with_venue:
            vals["venue_id"] = self.venue.id
        if with_result_fee:
            vals["result_fee_type_id"] = self.fee_type_result.id
        return self.env["federation.match"].create(vals)

    # ------------------------------------------------------------------
    # action_create_venue_finance_event tests
    # ------------------------------------------------------------------

    def test_venue_finance_event_created(self):
        """action_create_venue_finance_event creates a finance event for a venue match."""
        match = self._create_done_match(with_venue=True)
        events = match.action_create_venue_finance_event(
            fee_type_code="venue_booking",
            amount=150.0,
        )
        self.assertTrue(events, "Finance event should be created.")
        event = events[0]
        self.assertEqual(event.source_model, "federation.match")
        self.assertEqual(event.source_res_id, match.id)
        self.assertEqual(event.event_type, "charge")
        self.assertEqual(event.state, "draft")

    def test_venue_finance_event_helper_is_idempotent(self):
        """Test that venue finance event helper is idempotent."""
        match = self._create_done_match(with_venue=True)

        match.action_create_venue_finance_event(
            fee_type_code="venue_booking", amount=150.0
        )
        match.action_create_venue_finance_event(
            fee_type_code="venue_booking", amount=200.0
        )

        self.assertEqual(
            self.env["federation.finance.event"].search_count(
                [
                    ("fee_type_id", "=", self.fee_type_venue.id),
                    ("source_model", "=", "federation.match"),
                    ("source_res_id", "=", match.id),
                ]
            ),
            1,
        )

    def test_scheduling_match_with_venue_creates_automatic_venue_event(self):
        """Test that scheduling match with venue creates automatic venue event."""
        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
                "venue_id": self.venue.id,
            }
        )

        match.action_schedule()

        event = self.env["federation.finance.event"].search(
            [
                ("source_model", "=", "federation.match"),
                ("source_res_id", "=", match.id),
                ("fee_type_id", "=", self.fee_type_venue.id),
            ],
            limit=1,
        )
        self.assertTrue(event)
        self.assertEqual(event.state, "draft")

    def test_venue_finance_event_fails_without_venue(self):
        """action_create_venue_finance_event raises ValidationError if venue field is blank."""
        match = self._create_done_match(with_venue=False)
        with self.assertRaises(ValidationError):
            match.action_create_venue_finance_event(fee_type_code="venue_booking")

    def test_venue_finance_event_creates_fee_type_if_missing(self):
        """action_create_venue_finance_event creates a new fee type if it doesn't exist."""
        match = self._create_done_match(with_venue=True)
        events = match.action_create_venue_finance_event(
            fee_type_code="NEW_AUTO_CODE",
            amount=200.0,
        )
        self.assertTrue(events)
        fee_type = self.env["federation.fee.type"].search(
            [("code", "=", "NEW_AUTO_CODE")], limit=1
        )
        self.assertTrue(fee_type, "Fee type should be auto-created.")

    # ------------------------------------------------------------------
    # auto finance event on result approval
    # ------------------------------------------------------------------

    def test_no_finance_event_without_fee_type(self):
        """Approving a result without result_fee_type_id creates no finance event."""
        if not self.has_result_control:
            self.skipTest("result_control not installed.")
        match = self._create_done_match(with_venue=False, with_result_fee=False)
        # go through result pipeline
        match.action_submit_result()
        match.with_user(self.validator_user).action_verify_result()
        event_count_before = self.env["federation.finance.event"].search_count(
            [
                ("source_model", "=", "federation.match"),
                ("source_res_id", "=", match.id),
            ]
        )
        match.with_user(self.approver_user).action_approve_result()
        event_count_after = self.env["federation.finance.event"].search_count(
            [
                ("source_model", "=", "federation.match"),
                ("source_res_id", "=", match.id),
            ]
        )
        self.assertEqual(
            event_count_before,
            event_count_after,
            "No extra finance event should be created without fee type.",
        )

    def test_finance_event_created_on_result_approval(self):
        """When result_fee_type_id is set, approving a result auto-creates finance event."""
        if not self.has_result_control:
            self.skipTest("result_control not installed.")
        match = self._create_done_match(with_venue=False, with_result_fee=True)
        # go through result pipeline
        match.action_submit_result()
        match.with_user(self.validator_user).action_verify_result()
        match.with_user(self.approver_user).action_approve_result()

        events = self.env["federation.finance.event"].search(
            [
                ("source_model", "=", "federation.match"),
                ("source_res_id", "=", match.id),
            ]
        )
        self.assertTrue(events, "A finance event should be auto-created on approval.")
        event = events[0]
        self.assertEqual(event.fee_type_id, self.fee_type_result)
        self.assertEqual(event.event_type, "charge")
        self.assertEqual(event.state, "draft")
        self.assertEqual(event.amount, self.fee_type_result.default_amount)

    def test_result_approval_reuses_existing_finance_event(self):
        """Test that result approval reuses existing finance event."""
        if not self.has_result_control:
            self.skipTest("result_control not installed.")
        match = self._create_done_match(with_venue=False, with_result_fee=True)
        match.action_submit_result()
        match.with_user(self.validator_user).action_verify_result()
        match.with_user(self.approver_user).action_approve_result()
        match.with_user(self.approver_user).action_reset_result_to_draft()
        match.action_submit_result()
        match.with_user(self.validator_user).action_verify_result()
        match.with_user(self.approver_user).action_approve_result()

        self.assertEqual(
            self.env["federation.finance.event"].search_count(
                [
                    ("fee_type_id", "=", self.fee_type_result.id),
                    ("source_model", "=", "federation.match"),
                    ("source_res_id", "=", match.id),
                ]
            ),
            1,
        )

    def test_result_finance_events_compute(self):
        """result_finance_event_ids computed field returns events for this match."""
        if not self.has_result_control:
            self.skipTest("result_control not installed.")
        match = self._create_done_match(with_result_fee=True, with_venue=True)
        match.action_submit_result()
        match.with_user(self.validator_user).action_verify_result()
        match.with_user(self.approver_user).action_approve_result()
        self.assertTrue(match.result_finance_event_ids)
        for ev in match.result_finance_event_ids:
            self.assertEqual(ev.source_res_id, match.id)

    def test_result_approved_sets_official_standings(self):
        """After full pipeline, include_in_official_standings is True."""
        if not self.has_result_control:
            self.skipTest("result_control not installed.")
        match = self._create_done_match(with_result_fee=False, with_venue=False)
        self.assertFalse(match.include_in_official_standings)
        match.action_submit_result()
        match.with_user(self.validator_user).action_verify_result()
        match.with_user(self.approver_user).action_approve_result()
        self.assertTrue(
            match.include_in_official_standings,
            "include_in_official_standings should be True after approval.",
        )
