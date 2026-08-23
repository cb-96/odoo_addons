from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install", "sf_officiating_v2")
class TestV2OfficiatingContract(TransactionCase):
    def test_legacy_match_cannot_receive_referee_assignment(self):
        legacy_match = self.env["federation.match"].create(
            {
                "name": "Standalone legacy match",
                "tournament_id": self.env["federation.tournament"]
                .search([], limit=1)
                .id,
            }
        )
        referee = self.env["federation.referee"].create({"name": "V2 Guard Referee"})
        with self.assertRaises(ValidationError):
            self.env["federation.match.referee"].create(
                {"match_id": legacy_match.id, "referee_id": referee.id, "role": "head"}
            )

    def test_legacy_match_cannot_receive_club_duty(self):
        tournament = self.env["federation.tournament"].search([], limit=1)
        club = self.env["federation.club"].search([], limit=1)
        if not tournament or not club:
            self.skipTest("Requires tournament and club fixture data")
        legacy_match = self.env["federation.match"].create(
            {"name": "Standalone duty match", "tournament_id": tournament.id}
        )
        with self.assertRaises(ValidationError):
            self.env["federation.match.club.referee.duty"].create(
                {"match_id": legacy_match.id, "club_id": club.id, "role": "table"}
            )
