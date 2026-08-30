import hashlib
import json

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_publication")
class TestPhase511Integrity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        season = cls.env["federation.season"].create(
            {
                "name": "5.1.1 Season",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "5.1.1 Competition", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "5.1.1 Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        division = cls.env["federation.tournament"].create(
            {
                "name": "5.1.1 Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2026-10-01",
            }
        )
        participants = cls.env["federation.participant.set"].create(
            {
                "name": "5.1.1 Participants",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "state": "finalized",
            }
        )
        cls.structure = cls.env["federation.competition.structure"].create(
            {
                "name": "5.1.1 Structure",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "participant_set_id": participants.id,
                "format_type": "custom",
            }
        )
        cls.venue = cls.env["federation.venue"].create({"name": "5.1.1 Venue"})
        cls.days = cls.env["federation.matchday"].create(
            [
                {
                    "name": "Day A",
                    "edition_id": cls.edition.id,
                    "date": "2026-10-03",
                    "venue_id": cls.venue.id,
                    "state": "capacity_ready",
                },
                {
                    "name": "Day B",
                    "edition_id": cls.edition.id,
                    "date": "2026-10-10",
                    "venue_id": cls.venue.id,
                    "state": "capacity_ready",
                },
            ]
        )

    @staticmethod
    def _digest(snapshot):
        payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    @staticmethod
    def _snapshot():
        # Odoo stores an explicitly empty required Json value as NULL.
        return [{"fixture_id": 1}]

    def _schedule_review(self, day, suffix):
        snapshot = self._snapshot()
        schedule = self.env["federation.schedule"].create(
            {
                "name": f"Schedule {suffix}",
                "edition_id": self.edition.id,
                "structure_id": self.structure.id,
                "matchday_id": day.id,
                "state": "approved",
            }
        )
        review = (
            self.env["federation.schedule.review"]
            .sudo()
            .create(
                {
                    "schedule_id": schedule.id,
                    "submitted_revision": schedule.revision,
                    "state": "pending",
                    "assignment_snapshot": snapshot,
                    "snapshot_digest": self._digest(snapshot),
                    "submitted_by_id": self.env.user.id,
                }
            )
        )
        return schedule, review

    def _valid_schedule_review(self, day, suffix):
        stage = self.env["federation.structure.stage"].create(
            {
                "name": f"5.1.1 Stage {suffix}",
                "structure_id": self.structure.id,
                "stage_type": "league",
            }
        )
        club = self.env["federation.club"].create({"name": f"5.1.1 Club {suffix}"})
        teams = self.env["federation.team"].create(
            [
                {"name": f"5.1.1 Home {suffix}", "club_id": club.id},
                {"name": f"5.1.1 Away {suffix}", "club_id": club.id},
            ]
        )
        fixture = self.env["federation.fixture"].create(
            {
                "structure_id": self.structure.id,
                "stage_id": stage.id,
                "round_number": 1,
                "home_team_id": teams[0].id,
                "away_team_id": teams[1].id,
                "state": "ready",
            }
        )
        area = self.env["federation.playing.area"].create(
            {"name": f"5.1.1 Court {suffix}", "venue_id": self.venue.id}
        )
        slot = self.env["federation.schedule.slot"].create(
            {
                "matchday_id": day.id,
                "court_id": area.id,
                "start_datetime": "2026-10-03 09:00:00",
                "end_datetime": "2026-10-03 09:40:00",
            }
        )
        self.env["federation.matchday.allocation"].create(
            {
                "matchday_id": day.id,
                "structure_id": self.structure.id,
                "stage_id": stage.id,
                "round_number": 1,
            }
        )
        schedule = self.env["federation.schedule"].create(
            {
                "name": f"Valid Schedule {suffix}",
                "edition_id": self.edition.id,
                "structure_id": self.structure.id,
                "matchday_id": day.id,
            }
        )
        self.env["federation.schedule.assignment"].create(
            {
                "schedule_id": schedule.id,
                "fixture_id": fixture.id,
                "slot_id": slot.id,
            }
        )
        schedule.state = "approved"
        commands = self.env["federation.schedule.approval.commands"]
        snapshot = commands._snapshot(schedule)
        review = (
            self.env["federation.schedule.review"]
            .sudo()
            .create(
                {
                    "schedule_id": schedule.id,
                    "submitted_revision": schedule.revision,
                    "state": "pending",
                    "assignment_snapshot": snapshot,
                    "snapshot_digest": commands._digest(snapshot),
                    "submitted_by_id": self.env.user.id,
                }
            )
        )
        return schedule, review

    def test_review_decision_fields_reject_direct_writes(self):
        schedule, review = self._schedule_review(self.days[0], "guard")
        with self.assertRaises(ValidationError):
            review.sudo().write({"state": "approved"})
        review._write_decision(
            {"state": "approved", "reviewer_id": self.env.user.id}
        )
        self.assertEqual(review.state, "approved")
        self.assertEqual(schedule.state, "approved")

    def test_live_publications_are_independent_per_matchday(self):
        schedule_a, review_a = self._schedule_review(self.days[0], "A")
        schedule_b, review_b = self._schedule_review(self.days[1], "B")
        snapshot = self._snapshot()
        Publication = self.env["federation.schedule.publication"].sudo()
        publication_a = Publication.create(
            {
                "schedule_id": schedule_a.id,
                "version": 1,
                "assignment_snapshot": snapshot,
                "snapshot_digest": self._digest(snapshot),
                "source_revision": 0,
                "review_id": review_a.id,
            }
        )
        publication_b = Publication.create(
            {
                "schedule_id": schedule_b.id,
                "version": 1,
                "assignment_snapshot": snapshot,
                "snapshot_digest": self._digest(snapshot),
                "source_revision": 0,
                "review_id": review_b.id,
            }
        )
        self.assertEqual(publication_a.state, "live")
        self.assertEqual(publication_b.state, "live")
        self.assertNotEqual(publication_a.matchday_id, publication_b.matchday_id)

    def test_only_one_live_publication_is_allowed_per_matchday(self):
        schedule, review = self._schedule_review(self.days[0], "unique")
        snapshot = self._snapshot()
        vals = {
            "schedule_id": schedule.id,
            "version": 1,
            "assignment_snapshot": snapshot,
            "snapshot_digest": self._digest(snapshot),
            "source_revision": 0,
            "review_id": review.id,
        }
        self.env["federation.schedule.publication"].sudo().create(vals)
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.env["federation.schedule.publication"].sudo().create(
                    {**vals, "version": 2}
                )

    def test_schedule_approver_can_review_without_calendar_model_access(self):
        approver_group = self.env.ref(
            "sports_federation_schedule_approval.group_schedule_approver"
        )
        schedule, review = self._valid_schedule_review(self.days[0], "approver")
        approver = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Publication integrity Schedule Approver",
                    "login": "publication.schedule.approver@example.com",
                    "email": "publication.schedule.approver@example.com",
                    "group_ids": [(6, 0, [approver_group.id])],
                }
            )
        )
        self.env["federation.competition.role.assignment"].sudo().create(
            {
                "edition_id": self.edition.id,
                "role": "schedule_approver",
                "user_id": approver.id,
            }
        )

        review.with_user(approver).write({"review_note": "Reviewed and approved."})
        review.with_user(approver).action_approve_schedule()

        self.assertEqual(review.state, "approved")
        self.assertEqual(schedule.state, "approved")
        self.assertEqual(review.reviewer_id, approver)
        self.assertEqual(review.review_note, "Reviewed and approved.")
        with self.assertRaises(ValidationError):
            review.with_user(approver).write({"review_note": "Changed later."})

        publication = (
            self.env["federation.schedule.approval.commands"]
            .with_user(approver)
            .publish(schedule.id)
        )
        self.assertEqual(publication.state, "live")
        self.assertTrue(schedule.assignment_ids.fixture_id.operational_match_id)
        self.assertEqual(schedule.state, "published")

    def test_unassigned_schedule_approver_is_rejected_without_access_error(self):
        approver_group = self.env.ref(
            "sports_federation_schedule_approval.group_schedule_approver"
        )
        approver = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Publication integrity Unassigned Approver",
                    "login": "publication.unassigned.approver@example.com",
                    "email": "publication.unassigned.approver@example.com",
                    "group_ids": [(6, 0, [approver_group.id])],
                }
            )
        )

        with self.assertRaises(ValidationError):
            self.env["federation.competition.role.assignment"].with_user(
                approver
            ).assert_role(self.edition, "schedule_approver")
