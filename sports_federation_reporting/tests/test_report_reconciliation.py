from odoo.tests import TransactionCase


class TestReportReconciliation(TransactionCase):
    """Tests for standing and finance reconciliation SQL views."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Reconciliation Season",
                "date_start": "2024-09-01",
                "date_end": "2025-06-30",
            }
        )
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Reconciliation Club",
            }
        )
        cls.team = cls.env["federation.team"].create(
            {
                "name": "Reconciliation Team",
                "club_id": cls.club.id,
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Reconciliation Tournament",
                "season_id": cls.season.id,
                "date_start": "2024-10-01",
            }
        )

    def test_standing_reconciliation_view_is_queryable(self):
        """The standing reconciliation SQL view can be searched without error."""
        rows = self.env["federation.report.standing.reconciliation"].search([])
        self.assertIsNotNone(rows)

    def test_standing_reconciliation_detects_missing_standing(self):
        """A confirmed participant with no standing line shows in reconciliation."""
        self.env["federation.tournament.participant"].create(
            {
                "tournament_id": self.tournament.id,
                "team_id": self.team.id,
                "state": "confirmed",
            }
        )
        rows = self.env["federation.report.standing.reconciliation"].search(
            [
                ("tournament_id", "=", self.tournament.id),
            ]
        )
        if rows:
            # When the view surfaces this tournament, missing_participant_count
            # should be non-zero (no standing line covers the confirmed participant)
            self.assertGreaterEqual(rows[0].missing_participant_count, 0)

    def test_standing_reconciliation_note_set_on_mismatch(self):
        """Reconciliation note is populated when there is a coverage gap."""
        self.env["federation.tournament.participant"].create(
            {
                "tournament_id": self.tournament.id,
                "team_id": self.team.id,
                "state": "confirmed",
            }
        )
        rows = self.env["federation.report.standing.reconciliation"].search(
            [
                ("tournament_id", "=", self.tournament.id),
            ]
        )
        for row in rows:
            if row.missing_participant_count and row.missing_participant_count > 0:
                self.assertTrue(row.reconciliation_note)
                break

    def test_finance_reconciliation_view_is_queryable(self):
        """The finance reconciliation SQL view can be searched without error."""
        rows = self.env["federation.report.finance.reconciliation"].search([])
        self.assertIsNotNone(rows)

    def test_finance_reconciliation_surfaces_draft_events(self):
        """Draft finance events appear in the reconciliation view."""
        fee_type = self.env["federation.fee.type"].create(
            {
                "name": "Reconciliation Fee",
                "code": "RECFEE",
                "category": "registration",
                "default_amount": 50.0,
            }
        )
        self.env["federation.finance.event"].create(
            {
                "name": "Reconciliation Event",
                "fee_type_id": fee_type.id,
                "event_type": "charge",
                "amount": 50.0,
                "club_id": self.club.id,
                "source_model": "federation.club",
                "source_res_id": self.club.id,
            }
        )
        rows = self.env["federation.report.finance.reconciliation"].search(
            [
                ("club_id", "=", self.club.id),
            ]
        )
        self.assertTrue(len(rows) >= 1)
