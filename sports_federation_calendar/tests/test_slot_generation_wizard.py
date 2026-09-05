from datetime import datetime

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_calendar_slot_generation")
class TestMatchdaySlotGenerationWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.tz = "Europe/Brussels"
        season = cls.env["federation.season"].create(
            {
                "name": "Generator Season",
                "date_start": "2026-09-01",
                "date_end": "2027-06-30",
            }
        )
        competition = cls.env["federation.competition"].create(
            {"name": "Generator Competition", "competition_type": "league"}
        )
        edition = cls.env["federation.competition.edition"].create(
            {
                "name": "Generator Edition",
                "competition_id": competition.id,
                "season_id": season.id,
            }
        )
        cls.venue = cls.env["federation.venue"].create({"name": "Generator Venue"})
        cls.courts = cls.env["federation.playing.area"].create(
            [
                {"name": "Generator Court 1", "venue_id": cls.venue.id},
                {"name": "Generator Court 2", "venue_id": cls.venue.id},
            ]
        )
        cls.matchday = cls.env["federation.matchday"].create(
            {
                "name": "Generator Match Day",
                "edition_id": edition.id,
                "date": "2026-10-03",
                "venue_id": cls.venue.id,
            }
        )
        cls.env["federation.venue.blackout"].create(
            [
                {
                    "venue_id": cls.venue.id,
                    "playing_area_id": cls.courts[0].id,
                    "date_start": "2026-10-03 08:00:00",
                    "date_end": "2026-10-03 09:00:00",
                    "closure_type": "maintenance",
                },
                {
                    "venue_id": cls.venue.id,
                    "date_start": "2026-10-03 13:00:00",
                    "date_end": "2026-10-03 14:00:00",
                    "closure_type": "blackout",
                },
            ]
        )

    def _wizard(self, **overrides):
        values = {
            "matchday_id": self.matchday.id,
            "court_ids": [(6, 0, self.courts.ids)],
            "start_hour": 9.0,
            "end_hour": 17.0,
            "slot_duration_minutes": 60,
            "noon_pause": True,
            "noon_pause_minutes": 60,
        }
        values.update(overrides)
        return self.env["federation.matchday.slot.generation.wizard"].create(values)

    def test_preview_respects_noon_pause_and_venue_constraints(self):
        wizard = self._wizard()

        self.assertEqual(wizard.generated_slot_count, 11)
        self.assertEqual(wizard.pause_slot_count, 2)
        self.assertEqual(wizard.blocked_slot_count, 3)

    def test_generation_uses_local_time_and_creates_visible_pause(self):
        wizard = self._wizard()
        wizard.action_generate()

        available = self.matchday.slot_ids.filtered(
            lambda slot: slot.state == "available"
        )
        breaks = self.matchday.slot_ids.filtered(lambda slot: slot.state == "break")
        self.assertEqual(len(available), 11)
        self.assertEqual(len(breaks), 2)
        self.assertEqual(
            min(available.mapped("start_datetime")),
            datetime(2026, 10, 3, 7, 0),
        )
        self.assertTrue(all(slot.note == "Noon pause" for slot in breaks))
        self.assertFalse(
            available.filtered(
                lambda slot: datetime(2026, 10, 3, 10, 0) < slot.end_datetime
                and slot.start_datetime < datetime(2026, 10, 3, 11, 0)
            )
        )

    def test_existing_slots_require_explicit_replacement(self):
        self._wizard().action_generate()
        with self.assertRaises(ValidationError):
            self._wizard().action_generate()

        self._wizard(replace_existing_slots=True, end_hour=15.0).action_generate()
        self.assertEqual(
            self.matchday.default_slot_duration_minutes,
            60,
        )
        self.assertTrue(self.matchday.slot_ids)

    def test_generation_is_blocked_after_scheduling_starts(self):
        self.matchday.state = "scheduled"
        with self.assertRaises(ValidationError):
            self._wizard().action_generate()
