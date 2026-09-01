import hashlib
import json

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
        structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Operations Structure",
                "edition_id": cls.edition.id,
                "division_id": cls.division.id,
                "participant_set_id": participants.id,
                "format_type": "custom",
            }
        )
        venue = cls.env["federation.venue"].create({"name": "Operations Venue"})
        cls.court = cls.env["federation.playing.area"].create(
            {"name": "Court 1", "venue_id": venue.id}
        )
        cls.matchday = cls.env["federation.matchday"].create(
            {
                "name": "Operations Day",
                "edition_id": cls.edition.id,
                "date": "2026-10-03",
                "venue_id": venue.id,
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
        schedule = cls.env["federation.schedule"].create(
            {
                "name": "Operations Schedule",
                "edition_id": cls.edition.id,
                "structure_id": structure.id,
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
                    "schedule_id": schedule.id,
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
                    "schedule_id": schedule.id,
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
        session = self.env["federation.matchday.commands"].open_matchday(
            self.matchday.id
        )
        self.assertEqual(session.publication_id, self.publication)
        self.assertEqual(session.publication_digest, self.publication.snapshot_digest)
        self.assertEqual(self.matchday.state, "open")

    def test_operational_move_preserves_published_slot(self):
        self.env["federation.matchday.commands"].open_matchday(self.matchday.id)
        deviation = self.env["federation.matchday.commands"].record_schedule_deviation(
            self.matchday.id,
            self.match.id,
            "move",
            "Court turnaround",
            new_slot_id=self.slots[1].id,
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
