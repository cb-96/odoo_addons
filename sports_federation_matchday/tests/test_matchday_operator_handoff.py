import hashlib
import json
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_matchday_handoff")
class TestMatchdayOperatorHandoff(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        season = cls.env["federation.season"].create(
            {
                "name": "Operations Season",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Operations Competition", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Operations Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        cls.division = cls.env["federation.tournament"].create(
            {
                "name": "Operations Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2026-10-01",
            }
        )
        participants = cls.env["federation.participant.set"].create(
            {
                "name": "Operations Participants",
                "edition_id": cls.edition.id,
                "division_id": cls.division.id,
                "state": "finalized",
            }
        )
        cls.structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Operations Structure",
                "edition_id": cls.edition.id,
                "division_id": cls.division.id,
                "participant_set_id": participants.id,
                "format_type": "custom",
            }
        )
        cls.venue = cls.env["federation.venue"].create({"name": "Operations Venue"})
        cls.court = cls.env["federation.playing.area"].create(
            {"name": "Court 1", "venue_id": cls.venue.id}
        )
        cls.matchday = cls.env["federation.matchday"].create(
            {
                "name": "Operations Day",
                "edition_id": cls.edition.id,
                "date": "2026-10-03",
                "venue_id": cls.venue.id,
                "state": "scheduled",
            }
        )
        cls.slots = cls.env["federation.schedule.slot"].create(
            [
                {
                    "matchday_id": cls.matchday.id,
                    "court_id": cls.court.id,
                    "start_datetime": "2026-10-03 08:00:00",
                    "end_datetime": "2026-10-03 08:40:00",
                },
                {
                    "matchday_id": cls.matchday.id,
                    "court_id": cls.court.id,
                    "start_datetime": "2026-10-03 09:00:00",
                    "end_datetime": "2026-10-03 09:40:00",
                },
            ]
        )
        cls.schedule = cls.env["federation.schedule"].create(
            {
                "name": "Operations Schedule",
                "edition_id": cls.edition.id,
                "structure_id": cls.structure.id,
                "matchday_id": cls.matchday.id,
                "state": "published",
            }
        )
        snapshot = [{"fixture_id": 1}]
        digest = hashlib.sha256(
            json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        review = (
            cls.env["federation.schedule.review"]
            .sudo()
            .create(
                {
                    "schedule_id": cls.schedule.id,
                    "submitted_revision": 0,
                    "state": "pending",
                    "assignment_snapshot": snapshot,
                    "snapshot_digest": digest,
                    "submitted_by_id": cls.env.user.id,
                }
            )
        )
        review._write_decision({"state": "approved", "reviewer_id": cls.env.user.id})
        cls.publication = (
            cls.env["federation.schedule.publication"]
            .sudo()
            .create(
                {
                    "schedule_id": cls.schedule.id,
                    "version": 1,
                    "assignment_snapshot": snapshot,
                    "snapshot_digest": digest,
                    "source_revision": 0,
                    "review_id": review.id,
                }
            )
        )
        cls.matchday.sudo().write({"current_publication_id": cls.publication.id})
        cls.match = cls.env["federation.match"].create(
            {
                "tournament_id": cls.division.id,
                "date_scheduled": cls.slots[0].start_datetime,
                "state": "scheduled",
            }
        )
        cls.match.sudo().write(
            {
                "published_slot_id": cls.slots[0].id,
                "operational_slot_id": cls.slots[0].id,
                "operational_status": "as_published",
                "schedule_publication_id": cls.publication.id,
            }
        )
        cls.env["federation.competition.role.assignment"].create(
            {
                "edition_id": cls.edition.id,
                "role": "matchday_manager",
                "user_id": cls.env.user.id,
            }
        )

    def test_open_uses_exact_live_publication(self):
        result = self.env["federation.matchday.commands"].open_matchday(
            self.matchday.id
        )
        session = self.env["federation.matchday.session"].browse(
            result["session_id"]
        )
        self.assertEqual(session.publication_id, self.publication)
        self.assertEqual(session.publication_digest, self.publication.snapshot_digest)
        self.assertEqual(result["current_state"], "open")
        self.assertEqual(self.matchday.state, "open")

    def test_operational_move_preserves_published_slot(self):
        self.env["federation.matchday.commands"].open_matchday(self.matchday.id)
        result = self.env["federation.matchday.commands"].record_schedule_deviation(
            self.matchday.id,
            self.match.id,
            "move",
            "Court turnaround",
            new_slot_id=self.slots[1].id,
        )
        deviation = self.env["federation.matchday.deviation"].browse(
            result["deviation_id"]
        )
        self.assertEqual(self.match.published_slot_id, self.slots[0])
        self.assertEqual(self.match.operational_slot_id, self.slots[1])
        self.assertEqual(self.match.operational_status, "moved")
        self.assertEqual(deviation.publication_id, self.publication)
        with self.assertRaises(ValidationError):
            deviation.sudo().write({"reason": "Changed"})

    def test_change_rejected_before_matchday_is_open(self):
        with self.assertRaises(ValidationError):
            self.env["federation.matchday.commands"].record_schedule_deviation(
                self.matchday.id, self.match.id, "postpone", "Weather"
            )

    def test_restart_from_scratch_rejects_published_matchday(self):
        with self.assertRaisesRegex(ValidationError, "publication history"):
            self.matchday._assert_restartable_from_scratch()

    def test_unlink_draft_matchday_removes_mutable_schedule(self):
        matchday = self.env["federation.matchday"].create(
            {
                "name": "Discardable Day",
                "edition_id": self.edition.id,
                "date": "2026-10-17",
                "venue_id": self.venue.id,
            }
        )
        schedule = self.env["federation.schedule"].create(
            {
                "name": "Discardable Schedule",
                "edition_id": self.edition.id,
                "structure_id": self.structure.id,
                "matchday_id": matchday.id,
                "state": "draft",
            }
        )
        matchday_id = matchday.id
        schedule_id = schedule.id

        matchday.unlink()

        self.assertFalse(self.env["federation.matchday"].browse(matchday_id).exists())
        self.assertFalse(self.env["federation.schedule"].browse(schedule_id).exists())

    def test_unlink_published_matchday_preserves_schedule_history(self):
        with self.assertRaisesRegex(ValidationError, "publication history"):
            self.matchday.unlink()
        self.assertTrue(self.matchday.exists())
        self.assertTrue(
            self.env["federation.schedule"].search_count(
                [("matchday_id", "=", self.matchday.id)]
            )
        )

    def test_closed_delete_action_opens_before_reason_is_entered(self):
        self.matchday.sudo().write({"state": "closed"})

        action = self.matchday.action_open_closed_delete()
        wizard = self.env["federation.matchday.delete.wizard"].browse(action["res_id"])

        self.assertTrue(wizard.exists())
        self.assertFalse(
            self.env["federation.matchday.delete.wizard"].fields_get()["reason"][
                "required"
            ]
        )
        with self.assertRaisesRegex(ValidationError, "Enter a reason"):
            wizard.action_delete()

    def test_closed_matchday_delete_wizard_removes_impact_data(self):
        session = (
            self.env["federation.matchday.session"]
            .sudo()
            .create(
                {
                    "matchday_id": self.matchday.id,
                    "publication_id": self.publication.id,
                    "publication_digest": self.publication.snapshot_digest,
                    "state": "closed",
                    "closed_at": "2026-10-03 18:00:00",
                    "closed_by_id": self.env.user.id,
                    "close_note": "Test cleanup",
                }
            )
        )
        self.matchday.sudo().write({"state": "closed"})
        wizard = self.env["federation.matchday.delete.wizard"].create(
            {
                "matchday_id": self.matchday.id,
                "reason": "Remove test match day",
            }
        )

        self.assertIn("schedule(s)", wizard.impact_summary)
        wizard.action_delete()

        self.assertFalse(self.matchday.exists())
        self.assertFalse(
            self.env["federation.schedule"].browse(self.schedule.id).exists()
        )
        self.assertFalse(
            self.env["federation.schedule.publication"]
            .browse(self.publication.id)
            .exists()
        )
        self.assertFalse(session.exists())
        self.assertTrue(self.match.exists())
        self.assertFalse(self.match.schedule_publication_id)
        self.assertFalse(self.match.published_slot_id)
        self.assertFalse(self.match.operational_slot_id)

    def test_restart_from_scratch_creates_clean_replacement(self):
        original = self.env["federation.matchday"].create(
            {
                "name": "Mistaken Day",
                "edition_id": self.edition.id,
                "date": "2026-10-10",
                "venue_id": self.venue.id,
                "default_day_start_hour": 8.5,
                "default_slot_duration_minutes": 45,
            }
        )
        original_id = original.id
        wizard = self.env["federation.matchday.restart.wizard"].create(
            {
                "matchday_id": original.id,
                "reason": "Wrong divisions and capacity",
                "confirmation": True,
            }
        )

        action = wizard.action_restart()
        replacement = self.env["federation.matchday"].browse(action["res_id"])

        self.assertFalse(self.env["federation.matchday"].browse(original_id).exists())
        self.assertEqual(replacement.name, "Mistaken Day")
        self.assertEqual(replacement.state, "draft")
        self.assertEqual(replacement.date.isoformat(), "2026-10-10")
        self.assertEqual(replacement.venue_id, self.venue)
        self.assertEqual(replacement.default_day_start_hour, 8.5)
        self.assertEqual(replacement.default_slot_duration_minutes, 45)
        self.assertFalse(replacement.allocation_ids)
        self.assertFalse(replacement.slot_ids)

    def test_open_failure_rolls_back_session_and_court_statuses(self):
        transition = self.env["federation.workflow.transition"]
        with patch.object(
            type(transition),
            "execute",
            side_effect=RuntimeError("injected transition failure"),
        ), self.assertRaises(RuntimeError):
            self.env["federation.matchday.commands"].open_matchday(
                self.matchday.id
            )
        self.assertEqual(self.matchday.state, "scheduled")
        self.assertFalse(
            self.env["federation.matchday.session"].search(
                [("matchday_id", "=", self.matchday.id)]
            )
        )
        self.assertFalse(
            self.env["federation.matchday.court.status"].search(
                [("matchday_id", "=", self.matchday.id)]
            )
        )

    def test_open_and_deviation_emit_transition_audit(self):
        open_result = self.env["federation.matchday.commands"].open_matchday(
            self.matchday.id
        )
        self.env["federation.matchday.commands"].record_schedule_deviation(
            self.matchday.id,
            self.match.id,
            "move",
            "Audit move",
            new_slot_id=self.slots[1].id,
        )
        events = self.env["federation.audit.event"].search(
            [
                ("event_family", "=", "workflow_transition"),
                (
                    "event_type",
                    "in",
                    ["matchday_opened", "matchday_match_deviated"],
                ),
            ]
        )
        self.assertEqual(
            set(events.mapped("event_type")),
            {"matchday_opened", "matchday_match_deviated"},
        )
        self.assertTrue(open_result["session_id"])
