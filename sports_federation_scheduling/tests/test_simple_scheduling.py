from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_simple_scheduling")
class TestSimpleScheduling(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        season = cls.env["federation.season"].create(
            {"name": "Simple Season", "date_start": "2026-09-01", "date_end": "2027-06-30"}
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Simple Competition", "competition_type": "league"}
        )
        edition = cls.env["federation.competition.edition"].create(
            {"name": "Simple Edition", "competition_id": competition.id, "season_id": season.id}
        )
        division = cls.env["federation.tournament"].create(
            {
                "name": "Simple Division",
                "edition_id": edition.id,
                "competition_id": competition.id,
                "season_id": season.id,
                "date_start": "2026-10-01",
            }
        )
        participants = cls.env["federation.participant.set"].create(
            {
                "name": "Simple Participants",
                "edition_id": edition.id,
                "division_id": division.id,
                "state": "finalized",
            }
        )
        structure = cls.env["federation.competition.structure"].create(
            {
                "name": "Simple Structure",
                "edition_id": edition.id,
                "division_id": division.id,
                "participant_set_id": participants.id,
                "format_type": "custom",
                "state": "frozen",
            }
        )
        venue = cls.env["federation.venue"].create({"name": "Simple Venue"})
        matchday = cls.env["federation.matchday"].create(
            {
                "name": "Simple Match Day",
                "edition_id": edition.id,
                "date": "2026-10-10",
                "venue_id": venue.id,
                "state": "scheduled",
            }
        )
        cls.schedule = cls.env["federation.schedule"].create(
            {
                "name": "Simple Schedule",
                "edition_id": edition.id,
                "structure_id": structure.id,
                "matchday_id": matchday.id,
                "state": "draft",
            }
        )

    def _with_validation(self, validation):
        return patch.object(
            type(self.schedule), "_submission_validation", return_value=validation
        )

    def test_errors_are_must_fix_and_warnings_could_improve(self):
        validation = {
            "valid": False,
            "errors": [{"code": "slot_occupied", "message": "A slot contains more than one fixture."}] * 2,
            "warnings": [{"code": "rest", "message": "A team has little rest."}],
            "unassigned_fixture_ids": [1, 2, 3],
        }
        with self._with_validation(validation):
            self.schedule.invalidate_recordset()
            schedule = self.schedule
            self.assertTrue(schedule.simple_checked)
            self.assertEqual(schedule.must_fix_count, 5)
            self.assertEqual(schedule.could_improve_count, 1)
            self.assertIn("5 blocking conflicts", schedule.simple_summary)
            self.assertIn("1 preference warning", schedule.simple_summary)
            self.assertIn("A slot contains more than one fixture. (x2)", schedule.must_fix_html)
            self.assertIn("3 matches still need a court and time.", schedule.must_fix_html)
            self.assertIn("A team has little rest.", schedule.could_improve_html)
            self.assertNotIn("A team has little rest.", schedule.must_fix_html)

    def test_clean_schedule_has_nothing_to_fix(self):
        with self._with_validation(
            {"valid": True, "errors": [], "warnings": [], "unassigned_fixture_ids": []}
        ):
            self.schedule.invalidate_recordset()
            self.assertEqual(self.schedule.must_fix_count, 0)
            self.assertEqual(self.schedule.could_improve_count, 0)
            self.assertFalse(self.schedule.must_fix_html)

    def test_message_text_is_escaped(self):
        validation = {
            "valid": False,
            "errors": [{"message": "<script>alert(1)</script>"}],
            "warnings": [],
            "unassigned_fixture_ids": [],
        }
        with self._with_validation(validation):
            self.schedule.invalidate_recordset()
            self.assertNotIn("<script>", self.schedule.must_fix_html)

    def test_a_failing_check_is_never_reported_as_clean(self):
        with patch.object(
            type(self.schedule), "_submission_validation", side_effect=RuntimeError("boom")
        ):
            self.schedule.invalidate_recordset()
            self.assertTrue(self.schedule.simple_checked)
            self.assertEqual(self.schedule.must_fix_count, 1)

    def test_submitted_schedules_are_not_revalidated(self):
        self.schedule.sudo().write({"state": "ready_for_review"})
        with patch.object(
            type(self.schedule), "_submission_validation", side_effect=AssertionError("no")
        ):
            self.schedule.invalidate_recordset()
            self.assertFalse(self.schedule.simple_checked)

    def test_unsaved_schedule_has_no_status(self):
        draft = self.env["federation.schedule"].new({})
        self.assertFalse(draft.simple_checked)
        self.assertEqual(draft.simple_scheduled_count, 0)
