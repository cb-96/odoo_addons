from datetime import datetime

from odoo import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_calendar_slot_timeline")
class TestCalendarSlotTimeline(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.tz = "Europe/Brussels"
        season = cls.env["federation.season"].create({
            "name": "Slot Test 2026-2027", "date_start": "2026-09-01", "date_end": "2027-06-30"
        })
        competition = cls.env["federation.competition"].create({
            "name": "Slot Test Competition", "competition_type": "league"
        })
        edition = cls.env["federation.competition.edition"].create({
            "name": "Slot Test Edition", "competition_id": competition.id,
            "season_id": season.id, "date_start": "2026-10-03", "date_end": "2026-10-03"
        })
        cls.venue = cls.env["federation.venue"].create({"name": "Slot Test Venue"})
        cls.court_1 = cls.env["federation.playing.area"].create({"name": "Court 1", "venue_id": cls.venue.id})
        cls.court_2 = cls.env["federation.playing.area"].create({"name": "Court 2", "venue_id": cls.venue.id})
        cls.court_3 = cls.env["federation.playing.area"].create({"name": "Court 3", "venue_id": cls.venue.id})
        cls.matchday = cls.env["federation.matchday"].create({
            "name": "3 October", "edition_id": edition.id, "date": "2026-10-03",
            "venue_id": cls.venue.id, "default_day_start_hour": 9.0,
            "default_slot_duration_minutes": 40,
        })
        cls.Slot = cls.env["federation.schedule.slot"].with_context(default_matchday_id=cls.matchday.id)

    def _utc(self, hour, minute=0):
        # Europe/Brussels is UTC+2 on 3 October 2026.
        return datetime(2026, 10, 3, hour - 2, minute)

    def test_first_slot_of_each_court_uses_matchday_default(self):
        slots = self.Slot.create([
            {"matchday_id": self.matchday.id, "court_id": self.court_1.id, "start_datetime": self._utc(9), "end_datetime": self._utc(10)},
            {"matchday_id": self.matchday.id, "court_id": self.court_2.id, "start_datetime": self._utc(9), "end_datetime": self._utc(9, 40)},
            {"matchday_id": self.matchday.id, "court_id": self.court_3.id, "start_datetime": self._utc(9), "end_datetime": self._utc(9, 40)},
        ])
        self.assertEqual(slots[0].start_datetime, self._utc(9))
        self.assertEqual(slots[1].start_datetime, self._utc(9))
        self.assertEqual(slots[2].start_datetime, self._utc(9))

    def test_each_court_inherits_its_own_latest_duration(self):
        self.Slot.create({"matchday_id": self.matchday.id, "court_id": self.court_1.id, "start_datetime": self._utc(9), "end_datetime": self._utc(10)})
        self.Slot.create({"matchday_id": self.matchday.id, "court_id": self.court_2.id, "start_datetime": self._utc(9), "end_datetime": self._utc(9, 40)})
        court_1_next = self.Slot.create({"matchday_id": self.matchday.id, "court_id": self.court_1.id, "start_datetime": self._utc(9), "end_datetime": self._utc(9, 40)})
        court_2_next = self.Slot.create({"matchday_id": self.matchday.id, "court_id": self.court_2.id, "start_datetime": self._utc(9), "end_datetime": self._utc(10)})
        self.assertEqual((court_1_next.start_datetime, court_1_next.end_datetime), (self._utc(10), self._utc(11)))
        self.assertEqual((court_2_next.start_datetime, court_2_next.end_datetime), (self._utc(9, 40), self._utc(10, 20)))

    def test_buffered_rows_are_normalized_sequentially_per_court(self):
        slots = self.Slot.create([
            {"matchday_id": self.matchday.id, "court_id": self.court_1.id, "start_datetime": self._utc(9), "end_datetime": self._utc(10)},
            {"matchday_id": self.matchday.id, "court_id": self.court_2.id, "start_datetime": self._utc(9), "end_datetime": self._utc(9, 40)},
            {"matchday_id": self.matchday.id, "court_id": self.court_1.id, "start_datetime": self._utc(9), "end_datetime": self._utc(9, 40)},
            {"matchday_id": self.matchday.id, "court_id": self.court_2.id, "start_datetime": self._utc(9), "end_datetime": self._utc(9, 40)},
            {"matchday_id": self.matchday.id, "court_id": self.court_1.id, "start_datetime": self._utc(9), "end_datetime": self._utc(9, 40)},
        ])
        self.assertEqual((slots[2].start_datetime, slots[2].end_datetime), (self._utc(10), self._utc(11)))
        self.assertEqual((slots[3].start_datetime, slots[3].end_datetime), (self._utc(9, 40), self._utc(10, 20)))
        self.assertEqual((slots[4].start_datetime, slots[4].end_datetime), (self._utc(11), self._utc(12)))

    def test_court_onchange_uses_latest_saved_end_and_duration(self):
        self.Slot.create({"matchday_id": self.matchday.id, "court_id": self.court_1.id, "start_datetime": self._utc(9), "end_datetime": self._utc(10)})
        draft = self.Slot.new({"matchday_id": self.matchday.id, "court_id": self.court_1.id})
        draft._onchange_court_id()
        self.assertEqual((draft.start_datetime, draft.end_datetime), (self._utc(10), self._utc(11)))

    def test_manual_gap_is_preserved_when_continuation_disabled(self):
        self.Slot.create({"matchday_id": self.matchday.id, "court_id": self.court_1.id, "start_datetime": self._utc(9), "end_datetime": self._utc(10)})
        manual = self.Slot.create({"matchday_id": self.matchday.id, "court_id": self.court_1.id, "start_datetime": self._utc(13), "end_datetime": self._utc(14), "continue_court_timeline": False})
        self.assertEqual((manual.start_datetime, manual.end_datetime), (self._utc(13), self._utc(14)))

    def test_unsaved_inline_siblings_continue_without_parent_save(self):
        draft = self.matchday.new({
            "slot_ids": [
                Command.create({
                    "court_id": self.court_1.id,
                    "start_datetime": self._utc(9),
                    "end_datetime": self._utc(10),
                }),
                Command.create({
                    "court_id": self.court_1.id,
                    "start_datetime": self._utc(9),
                    "end_datetime": self._utc(9, 40),
                }),
                Command.create({
                    "court_id": self.court_2.id,
                    "start_datetime": self._utc(9),
                    "end_datetime": self._utc(9, 40),
                }),
            ]
        })
        first, second, other_court = draft.slot_ids
        second._onchange_court_id()
        self.assertEqual(
            (second.start_datetime, second.end_datetime),
            (self._utc(10), self._utc(11)),
        )
        third = self.env["federation.schedule.slot"].new({
            "matchday_id": draft,
            "court_id": self.court_1.id,
            "start_datetime": self._utc(9),
            "end_datetime": self._utc(9, 40),
        })
        draft.slot_ids += third
        third._onchange_court_id()
        self.assertEqual(
            (third.start_datetime, third.end_datetime),
            (self._utc(11), self._utc(12)),
        )
        other_court._onchange_court_id()
        self.assertEqual(
            (other_court.start_datetime, other_court.end_datetime),
            (self._utc(9), self._utc(9, 40)),
        )

