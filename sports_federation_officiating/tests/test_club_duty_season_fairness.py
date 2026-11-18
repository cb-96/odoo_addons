from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.sports_federation_officiating import duty_season_balance

T10 = ("2026-11-21 10:00:00", "2026-11-21 11:00:00")
T12 = ("2026-11-21 12:00:00", "2026-11-21 13:00:00")
T14 = ("2026-11-21 14:00:00", "2026-11-21 15:00:00")


def _fixture(number, slot, opponents, club=None, pinned=False):
    return {
        "assignment": number,
        "fixture": number,
        "start": slot[0],
        "end": slot[1],
        "duration_minutes": 60,
        "roles": ["table"] if club else [],
        "opponents": list(opponents),
        "club": club,
        "fallback": False,
        "pinned": pinned,
        "existing_clubs": [],
    }


@tagged("post_install", "-at_install", "sf_officiating", "sf_club_duty_planning")
class TestClubDutySeasonBalance(TransactionCase):
    def _balance(self, rows, **options):
        geometry = rows + [_fixture(1, T10, (1, 2))]
        return duty_season_balance.rebalance_season(rows, geometry, **options)

    def _rows(self, pinned=False):
        return [
            _fixture(2, T12, (3, 4), club=1, pinned=pinned),
            _fixture(3, T14, (5, 6), club=1),
        ]

    def test_over_target_club_sheds_duties(self):
        rows, report = self._balance(
            self._rows(), season_minutes={1: 600}, targets={1: 300, 2: 300}
        )
        self.assertEqual([row["club"] for row in rows], [2, 2])
        self.assertLess(report["objective_after"], report["objective_before"])

    def test_pinned_fixture_keeps_its_club(self):
        rows, _report = self._balance(
            self._rows(pinned=True), season_minutes={1: 600}, targets={1: 300, 2: 300}
        )
        self.assertEqual([row["club"] for row in rows], [1, 2])

    def test_ledger_domain_view_and_hooks_resolve(self):
        duties = self.env["federation.match.club.referee.duty"]
        duties.search(
            [
                (
                    "match_id.schedule_publication_id.schedule_id.edition_id."
                    "season_id",
                    "=",
                    0,
                )
            ]
        )
        schedules = self.env["federation.schedule"]
        for name in (
            "_club_duty_season_load",
            "_club_duty_target_minutes",
            "_club_duty_fairness_rebalance",
        ):
            self.assertTrue(callable(getattr(schedules, name)))
        self.assertTrue(
            self.env.ref(
                "sports_federation_officiating."
                "view_club_officiating_capacity_form_season_target"
            )
        )
        self.assertIn(
            "season_target_minutes",
            self.env["federation.club.officiating.capacity"]._fields,
        )
