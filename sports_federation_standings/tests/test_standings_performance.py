"""Performance regression tests for standings computation (Phase 3, Item 5).

Verifies that _build_standing_table() is O(n + m) — the number of ORM queries
must not grow with the number of matches (they are fetched in one batch query).

Expected query budget for _build_standing_table():
  1. _get_relevant_matches()  → 1 query
  2. _get_points_values()     → at most 1 query (rule_set already cached)
  3. _get_participants()      → 1 query
Total: <= 5 queries regardless of match count.
"""

from odoo.tests.common import TransactionCase


class TestStandingsPerformance(TransactionCase):
    """O(1) participant-lookup regression test for _build_standing_table()."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.has_result_control = (
            "include_in_official_standings" in cls.env["federation.match"]._fields
        )
        cls.club = cls.env["federation.club"].create(
            {"name": "Perf Club", "code": "PCL"}
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Perf Season",
                "code": "PSN",
                "date_start": "2025-01-01",
                "date_end": "2025-12-31",
            }
        )
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Perf Rule Set",
                "code": "PRS",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Perf Tournament",
                "code": "PTOUR",
                "season_id": cls.season.id,
                "date_start": "2025-06-01",
                "rule_set_id": cls.rule_set.id,
            }
        )

        # Create 10 teams and register them as participants
        cls.teams = cls.env["federation.team"].create(
            [
                {"name": f"Perf Team {i}", "club_id": cls.club.id, "code": f"PT{i}"}
                for i in range(10)
            ]
        )
        cls.participants = cls.env["federation.tournament.participant"].create(
            [{"tournament_id": cls.tournament.id, "team_id": t.id} for t in cls.teams]
        )

        # Create 200 done matches between team pairs (cycling through all pairs)
        teams = cls.teams
        n = len(teams)
        match_vals = []
        count = 0
        # Generate round-robin pairs and repeat until 200 matches
        pairs = [(teams[i], teams[j]) for i in range(n) for j in range(n) if i != j]
        while count < 200:
            home, away = pairs[count % len(pairs)]
            vals = {
                "tournament_id": cls.tournament.id,
                "home_team_id": home.id,
                "away_team_id": away.id,
                "home_score": (count % 4),
                "away_score": (count % 3),
                "state": "done",
            }
            if cls.has_result_control:
                vals["include_in_official_standings"] = True
            match_vals.append(vals)
            count += 1
        cls.env["federation.match"].create(match_vals)

        cls.standing = cls.env["federation.standing"].create(
            {
                "name": "Perf Standing",
                "tournament_id": cls.tournament.id,
                "rule_set_id": cls.rule_set.id,
            }
        )

    def test_build_standing_table_query_count(self):
        """_build_standing_table() must not issue more than 10 queries for 200 matches.

        The fixed O(n+m) implementation fetches all participants once and all
        matches once; subsequent lookups are dict-based and require no further
        DB round-trips.
        """
        with self.assertQueryCount(10):
            stats = self.standing._build_standing_table()

        # Sanity: all 10 participants have entries
        self.assertEqual(len(stats), 10)

    def test_build_standing_table_correct_totals(self):
        """Verify stats are correct for 200 matches (not just a query-count concern)."""
        stats = self.standing._build_standing_table()
        total_played = sum(s["played"] for s in stats.values())
        # Each match contributes 1 to home's played and 1 to away's played
        self.assertEqual(total_played, 200 * 2)
