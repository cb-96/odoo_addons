from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_schedule_amendment")
@tagged("sf_release_focus")
class TestScheduleAmendment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        season = cls.env["federation.season"].create(
            {
                "name": "Amendment Season",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Amendment Competition", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Amendment Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        division = cls.env["federation.tournament"].create(
            {
                "name": "Amendment Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2026-10-01",
            }
        )
        participants = cls.env["federation.participant.set"].create(
            {
                "name": "Amendment Participants",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "state": "finalized",
            }
        )
        structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Amendment Structure",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "participant_set_id": participants.id,
                "format_type": "custom",
                "state": "frozen",
            }
        )
        venue = cls.env["federation.venue"].create({"name": "Amendment Venue"})
        cls.matchday = cls.env["federation.matchday"].create(
            {
                "name": "Amendment Match Day",
                "edition_id": cls.edition.id,
                "date": "2026-10-10",
                "venue_id": venue.id,
                "state": "scheduled",
            }
        )
        cls.schedule = cls.env["federation.schedule"].create(
            {
                "name": "Published Schedule",
                "edition_id": cls.edition.id,
                "structure_id": structure.id,
                "matchday_id": cls.matchday.id,
                "state": "draft",
                "revision": 3,
            }
        )
        cls.structure = structure
        stage = cls.env["federation.structure.stage"].create(
            {"name": "League", "structure_id": structure.id, "stage_type": "league"}
        )
        cls.stage = stage
        fixture = cls.env["federation.fixture"].create(
            {"structure_id": structure.id, "stage_id": stage.id, "round_number": 1}
        )
        cls.fixture = fixture
        cls.allocation = cls.env["federation.matchday.allocation"].create(
            {
                "matchday_id": cls.matchday.id,
                "structure_id": structure.id,
                "stage_id": stage.id,
                "round_number": 1,
            }
        )
        court = cls.env["federation.playing.area"].create(
            {"name": "Main Court", "venue_id": venue.id}
        )
        slot = cls.env["federation.schedule.slot"].create(
            {
                "matchday_id": cls.matchday.id,
                "court_id": court.id,
                "start_datetime": "2026-10-10 10:00:00",
                "end_datetime": "2026-10-10 11:00:00",
            }
        )
        cls.env["federation.schedule.assignment"].create(
            {
                "schedule_id": cls.schedule.id,
                "fixture_id": fixture.id,
                "slot_id": slot.id,
            }
        )
        cls.schedule.state = "published"
        cls.env["federation.competition.role.assignment"].create(
            {
                "edition_id": cls.edition.id,
                "user_id": cls.env.user.id,
                "role": "schedule_planner",
            }
        )

    def test_published_schedule_creates_linked_replacement(self):
        replacement = self.schedule.action_create_revision("Late fixture added")
        self.assertEqual(self.schedule.state, "superseded")
        self.assertEqual(replacement.state, "changes_requested")
        self.assertEqual(replacement.supersedes_id, self.schedule)
        self.assertEqual(self.schedule.superseded_by_id, replacement)
        self.assertEqual(replacement.revision_reason, "Late fixture added")

    def test_replacement_copies_assignments_without_mutating_source(self):
        original = self.schedule.assignment_ids
        replacement = self.schedule.action_create_revision("Copy assignments")
        self.assertEqual(len(replacement.assignment_ids), len(original))
        self.assertEqual(
            set(replacement.assignment_ids.mapped("fixture_id").ids),
            set(original.mapped("fixture_id").ids),
        )
        self.assertEqual(
            set(replacement.assignment_ids.mapped("slot_id").ids),
            set(original.mapped("slot_id").ids),
        )
        self.assertTrue(
            original.filtered(lambda item: item.schedule_id == self.schedule)
        )

    def test_only_one_replacement_can_be_created(self):
        replacement = self.schedule.action_create_revision("First replacement")
        self.assertEqual(self.schedule.superseded_by_id, replacement)
        with self.assertRaises(ValidationError):
            self.schedule.action_create_revision("Second replacement")
        self.assertEqual(self.schedule.superseded_by_id, replacement)

    def test_reason_is_required(self):
        with self.assertRaises(ValidationError):
            self.schedule.action_create_revision("  ")

    def test_open_matchday_cannot_be_amended(self):
        self.matchday.state = "open"
        with self.assertRaises(ValidationError):
            self.schedule.action_create_revision("Unsafe live change")

    def _add_second_division_fixture(self):
        division = self.env["federation.tournament"].create(
            {
                "name": "Additional Division",
                "edition_id": self.edition.id,
                "competition_id": self.edition.competition_id.id,
                "season_id": self.edition.season_id.id,
                "date_start": "2026-10-01",
            }
        )
        participants = self.env["federation.participant.set"].create(
            {
                "name": "Additional Division Participants",
                "edition_id": self.edition.id,
                "division_id": division.id,
                "state": "finalized",
            }
        )
        structure = self.env["federation.competition.structure"].create(
            {
                "name": "Additional Division Structure",
                "edition_id": self.edition.id,
                "division_id": division.id,
                "participant_set_id": participants.id,
                "format_type": "custom",
                "state": "frozen",
            }
        )
        stage = self.env["federation.structure.stage"].create(
            {
                "name": "Additional Division League",
                "structure_id": structure.id,
                "stage_type": "league",
            }
        )
        clubs = self.env["federation.club"].create(
            [{"name": "Additional Home Club"}, {"name": "Additional Away Club"}]
        )
        teams = self.env["federation.team"].create(
            [
                {"name": "Additional Home", "club_id": clubs[0].id},
                {"name": "Additional Away", "club_id": clubs[1].id},
            ]
        )
        fixture = self.env["federation.fixture"].create(
            {
                "structure_id": structure.id,
                "stage_id": stage.id,
                "round_number": 1,
                "home_team_id": teams[0].id,
                "away_team_id": teams[1].id,
                "state": "ready",
            }
        )
        self.env["federation.matchday.allocation"].create(
            {
                "matchday_id": self.matchday.id,
                "structure_id": structure.id,
                "stage_id": stage.id,
                "round_number": 1,
            }
        )
        return fixture

    def test_revision_and_auto_planner_include_new_division_fixture(self):
        replacement = self.schedule.action_create_revision(
            "Add another division to the match day"
        )
        original_clubs = self.env["federation.club"].create(
            [{"name": "Original Home Club"}, {"name": "Original Away Club"}]
        )
        original_teams = self.env["federation.team"].create(
            [
                {"name": "Original Home", "club_id": original_clubs[0].id},
                {"name": "Original Away", "club_id": original_clubs[1].id},
            ]
        )
        self.fixture.write(
            {
                "home_team_id": original_teams[0].id,
                "away_team_id": original_teams[1].id,
                "state": "ready",
            }
        )
        fixture = self._add_second_division_fixture()
        court = self.schedule.assignment_ids.slot_id.court_id
        self.env["federation.schedule.slot"].create(
            {
                "matchday_id": self.matchday.id,
                "court_id": court.id,
                "start_datetime": "2026-10-10 11:00:00",
                "end_datetime": "2026-10-10 12:00:00",
            }
        )

        replacement.invalidate_recordset()
        proposal = self.env["federation.schedule.fairness.solver"].propose(replacement)

        self.assertIn(fixture, replacement.available_fixture_ids)
        self.assertIn(fixture, replacement.unassigned_fixture_ids)
        self.assertIn(
            fixture.id,
            [assignment["fixture_id"] for assignment in proposal["assignments"]],
        )

    def test_late_fixture_can_be_added_to_revision_and_removed_again(self):
        replacement = self.schedule.action_create_revision("Late fixture added")
        late_fixture = self.env["federation.fixture"].create(
            {
                "structure_id": self.structure.id,
                "stage_id": self.stage.id,
                "round_number": 2,
            }
        )
        self.allocation.manual_fixture_ids = [(4, late_fixture.id)]
        replacement.invalidate_recordset()
        self.assertIn(late_fixture, replacement.available_fixture_ids)
        self.assertIn(late_fixture, replacement.unassigned_fixture_ids)
        self.allocation.manual_fixture_ids = [(3, late_fixture.id)]
        replacement.invalidate_recordset()
        self.assertNotIn(late_fixture, replacement.available_fixture_ids)
