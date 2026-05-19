"""
Tests: standings computation excludes contested / unapproved results.

These tests verify that `_get_relevant_matches` in `FederationStanding`
only counts matches that are officially approved for standings.  They work
in two scenarios:

1. ``sports_federation_result_control`` is **installed**: the
   ``include_in_official_standings`` field is present on
   ``federation.match``.  Tests assert that contested/unapproved matches
   are filtered out automatically.
2. ``sports_federation_result_control`` is **not installed**: the field is
   absent and all ``state='done'`` matches are counted (fallback).

Scenario detection is done by checking ``include_in_official_standings`` in
``self.env["federation.match"]._fields`` at runtime.
"""

from odoo.tests.common import TransactionCase


class TestStandingsResultFilter(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "Filter Test Club",
                "code": "FTC",
            }
        )
        cls.team_a = cls.env["federation.team"].create(
            {
                "name": "Filter Team A",
                "club_id": cls.club.id,
                "code": "FTA",
            }
        )
        cls.team_b = cls.env["federation.team"].create(
            {
                "name": "Filter Team B",
                "club_id": cls.club.id,
                "code": "FTB",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Filter Season",
                "code": "FS2024",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Filter Tournament",
                "code": "FTOUR",
                "season_id": cls.season.id,
                "date_start": "2024-06-01",
            }
        )
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Filter Rule Set",
                "code": "FRS",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )
        cls.participant_a = cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_a.id,
            }
        )
        cls.participant_b = cls.env["federation.tournament.participant"].create(
            {
                "tournament_id": cls.tournament.id,
                "team_id": cls.team_b.id,
            }
        )
        cls.standing = cls.env["federation.standing"].create(
            {
                "name": "Filter Standing",
                "tournament_id": cls.tournament.id,
                "rule_set_id": cls.rule_set.id,
            }
        )
        cls.has_result_control = (
            "include_in_official_standings" in cls.env["federation.match"]._fields
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_match(self, home_score=2, away_score=1, state="done", official=True):
        """Create a match and optionally set official standings flag."""
        match = self.env["federation.match"].create(
            {
                "tournament_id": self.tournament.id,
                "home_team_id": self.team_a.id,
                "away_team_id": self.team_b.id,
                "home_score": home_score,
                "away_score": away_score,
                "state": state,
            }
        )
        if self.has_result_control:
            match.write({"include_in_official_standings": official})
        return match

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_approved_match_counted_in_standings(self):
        """An approved (official) match is included in standings computation."""
        match = self._create_match(home_score=3, away_score=0, official=True)
        relevant = self.standing._get_relevant_matches()
        self.assertIn(match, relevant, "Approved match should be included.")

    def test_contested_match_excluded_when_result_control_installed(self):
        """A contested match (include_in_official_standings=False) is excluded."""
        if not self.has_result_control:
            self.skipTest("result_control module not installed; field absent.")
        match = self._create_match(home_score=3, away_score=0, official=False)
        relevant = self.standing._get_relevant_matches()
        self.assertNotIn(match, relevant, "Contested match should not be counted.")

    def test_mixed_matches_only_approved_counted(self):
        """With two done matches (one official, one not), only official counted."""
        if not self.has_result_control:
            self.skipTest("result_control module not installed.")
        # Create a separate standing without overlapping matches from setUpClass
        tournament2 = self.env["federation.tournament"].create(
            {
                "name": "Mixed Filter Tournament",
                "code": "MFTOUR",
                "season_id": self.season.id,
                "date_start": "2024-07-01",
            }
        )
        team_c = self.env["federation.team"].create(
            {
                "name": "Team C",
                "club_id": self.club.id,
                "code": "TC2",
            }
        )
        team_d = self.env["federation.team"].create(
            {
                "name": "Team D",
                "club_id": self.club.id,
                "code": "TD2",
            }
        )
        self.env["federation.tournament.participant"].create(
            {
                "tournament_id": tournament2.id,
                "team_id": team_c.id,
            }
        )
        self.env["federation.tournament.participant"].create(
            {
                "tournament_id": tournament2.id,
                "team_id": team_d.id,
            }
        )
        standing2 = self.env["federation.standing"].create(
            {
                "name": "Mixed Standing",
                "tournament_id": tournament2.id,
                "rule_set_id": self.rule_set.id,
            }
        )

        approved_match = self.env["federation.match"].create(
            {
                "tournament_id": tournament2.id,
                "home_team_id": team_c.id,
                "away_team_id": team_d.id,
                "home_score": 2,
                "away_score": 0,
                "state": "done",
                "include_in_official_standings": True,
            }
        )
        contested_match = self.env["federation.match"].create(
            {
                "tournament_id": tournament2.id,
                "home_team_id": team_d.id,
                "away_team_id": team_c.id,
                "home_score": 1,
                "away_score": 1,
                "state": "done",
                "include_in_official_standings": False,
            }
        )

        relevant = standing2._get_relevant_matches()
        self.assertIn(approved_match, relevant)
        self.assertNotIn(contested_match, relevant)

    def test_draft_match_not_counted(self):
        """A match in draft state is never counted regardless of flags."""
        match = self._create_match(state="draft", official=True)
        relevant = self.standing._get_relevant_matches()
        self.assertNotIn(match, relevant, "Draft match should not count.")

    def test_cancelled_match_not_counted(self):
        """A cancelled match is never counted."""
        match = self._create_match(state="cancelled", official=True)
        relevant = self.standing._get_relevant_matches()
        self.assertNotIn(match, relevant, "Cancelled match should not count.")

    def test_recompute_with_only_official_results(self):
        """action_recompute includes only official results in the final table."""
        if not self.has_result_control:
            self.skipTest("result_control module not installed.")

        tournament3 = self.env["federation.tournament"].create(
            {
                "name": "Recompute Filter Tourney",
                "code": "RFT",
                "season_id": self.season.id,
                "date_start": "2024-08-01",
            }
        )
        team_e = self.env["federation.team"].create(
            {"name": "Team E", "club_id": self.club.id, "code": "TE"}
        )
        team_f = self.env["federation.team"].create(
            {"name": "Team F", "club_id": self.club.id, "code": "TF"}
        )
        part_e = self.env["federation.tournament.participant"].create(
            {"tournament_id": tournament3.id, "team_id": team_e.id}
        )
        part_f = self.env["federation.tournament.participant"].create(
            {"tournament_id": tournament3.id, "team_id": team_f.id}
        )

        standing3 = self.env["federation.standing"].create(
            {
                "name": "Recompute Filter Standing",
                "tournament_id": tournament3.id,
                "rule_set_id": self.rule_set.id,
            }
        )

        # Approved match: E wins 3-0
        self.env["federation.match"].create(
            {
                "tournament_id": tournament3.id,
                "home_team_id": team_e.id,
                "away_team_id": team_f.id,
                "home_score": 3,
                "away_score": 0,
                "state": "done",
                "include_in_official_standings": True,
            }
        )
        # Contested match: F wins 2-0 — must NOT count
        self.env["federation.match"].create(
            {
                "tournament_id": tournament3.id,
                "home_team_id": team_f.id,
                "away_team_id": team_e.id,
                "home_score": 2,
                "away_score": 0,
                "state": "done",
                "include_in_official_standings": False,
            }
        )

        standing3.action_recompute()
        lines = standing3.line_ids.sorted(key=lambda ln: ln.rank)
        self.assertEqual(len(lines), 2, "Both participants should have lines.")
        # E should be rank 1 (3 pts) because the contested F win is excluded
        e_line = lines.filtered(lambda ln: ln.participant_id == part_e)
        f_line = lines.filtered(lambda ln: ln.participant_id == part_f)
        self.assertTrue(e_line, "Team E line missing.")
        self.assertTrue(f_line, "Team F line missing.")
        self.assertGreater(
            e_line.points,
            f_line.points,
            "Team E (approved win) should have more points than Team F.",
        )
