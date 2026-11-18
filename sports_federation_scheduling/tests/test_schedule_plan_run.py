from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_schedule_plan_run")
class TestSchedulePlanRun(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        season = cls.env["federation.season"].create(
            {
                "name": "Planning Run Season",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Planning Run Competition", "competition_type": "league"}
        )
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Planning Run Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        division = cls.env["federation.tournament"].create(
            {
                "name": "Planning Run Division",
                "edition_id": cls.edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2026-10-01",
            }
        )
        participant_set = cls.env["federation.participant.set"].create(
            {
                "name": "Planning Run Participants",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "state": "finalized",
            }
        )
        structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Planning Run Structure",
                "edition_id": cls.edition.id,
                "division_id": division.id,
                "participant_set_id": participant_set.id,
                "format_type": "custom",
                "state": "frozen",
            }
        )
        stage = cls.env["federation.structure.stage"].create(
            {
                "name": "Planning Run Stage",
                "structure_id": structure.id,
                "stage_type": "league",
            }
        )
        clubs = cls.env["federation.club"].create(
            [{"name": "Planning Home Club"}, {"name": "Planning Away Club"}]
        )
        teams = cls.env["federation.team"].create(
            [
                {"name": "Planning Home", "club_id": clubs[0].id},
                {"name": "Planning Away", "club_id": clubs[1].id},
            ]
        )
        cls.fixture = cls.env["federation.fixture"].create(
            {
                "structure_id": structure.id,
                "stage_id": stage.id,
                "round_number": 1,
                "home_team_id": teams[0].id,
                "away_team_id": teams[1].id,
                "state": "ready",
            }
        )
        venue = cls.env["federation.venue"].create({"name": "Planning Run Venue"})
        matchday = cls.env["federation.matchday"].create(
            {
                "name": "Planning Run Day",
                "edition_id": cls.edition.id,
                "date": "2026-10-10",
                "venue_id": venue.id,
                "state": "scheduled",
            }
        )
        cls.env["federation.matchday.allocation"].create(
            {
                "matchday_id": matchday.id,
                "structure_id": structure.id,
                "manual_fixture_ids": [(6, 0, cls.fixture.ids)],
                "manual_only": True,
            }
        )
        court = cls.env["federation.playing.area"].create(
            {"name": "Planning Run Court", "venue_id": venue.id}
        )
        cls.slot = cls.env["federation.schedule.slot"].create(
            {
                "matchday_id": matchday.id,
                "court_id": court.id,
                "start_datetime": "2026-10-10 10:00:00",
                "end_datetime": "2026-10-10 11:00:00",
            }
        )
        cls.schedule = cls.env["federation.schedule"].create(
            {
                "name": "Planning Run Schedule",
                "edition_id": cls.edition.id,
                "structure_id": structure.id,
                "matchday_id": matchday.id,
            }
        )
        cls.env["federation.competition.role.assignment"].create(
            {
                "edition_id": cls.edition.id,
                "user_id": cls.env.user.id,
                "role": "schedule_planner",
            }
        )

    def _run(self):
        run = self.env["federation.schedule.plan.run"].create(
            {"schedule_id": self.schedule.id, "plan_type": "schedule"}
        )
        run.action_prepare()
        return run

    def test_apply_and_rollback_restore_the_exact_assignment_snapshot(self):
        run = self._run()
        self.assertEqual(run.state, "ready")
        self.assertEqual(run.source_revision, 0)
        self.assertEqual(run.proposal["assignments"][0]["fixture_id"], self.fixture.id)

        run.action_apply()
        self.assertEqual(run.state, "applied")
        self.assertEqual(self.schedule.assignment_ids.fixture_id, self.fixture)
        self.assertEqual(self.schedule.assignment_ids.slot_id, self.slot)
        self.assertEqual(self.schedule.revision, 1)

        run.action_rollback()
        self.assertEqual(run.state, "rolled_back")
        self.assertFalse(self.schedule.assignment_ids)
        self.assertEqual(self.schedule.revision, 2)
        self.assertEqual(self.schedule.change_ids[:1].command, "planning_run_rollback")

    def test_changed_slot_rejects_a_stale_run(self):
        run = self._run()
        self.slot.end_datetime = "2026-10-10 11:05:00"

        with self.assertRaises(UserError):
            run.action_apply()

        self.assertEqual(run.state, "ready")
        self.assertFalse(self.schedule.assignment_ids)

    def test_evidence_fields_cannot_be_overwritten_directly(self):
        run = self.env["federation.schedule.plan.run"].create(
            {"schedule_id": self.schedule.id, "plan_type": "schedule"}
        )

        with self.assertRaises(UserError):
            run.write({"proposal": {"assignments": []}})
