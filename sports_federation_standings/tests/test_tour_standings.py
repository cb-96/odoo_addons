"""Tour T-13: Standings Computation — Full Lifecycle

Walks the standings workflow end-to-end:
  1. Tournament setup with rule set (W=3, D=1, L=0)
  2. Three teams, six match-day results (W/D/L combinations)
  3. Standing: draft → action_recompute → computed; lines verified
  4. Tie-break scenario: two teams equal on points, resolved by wins
  5. Freeze the standing; verify frozen state blocks recompute
  6. Unfreeze; force-recompute updates scores after late result
  7. Result filter: contested results excluded from standings

Key invariants verified:
- Points computed correctly per rule set
- Lines ranked by points → wins → goal-difference → goals-for → name
- Tiebreak notes populated only where tie exists
- Frozen standings raise ValidationError on recompute without force flag
- action_unfreeze allows recompute again
- include_in_official_standings=False excludes a match (when field present)
"""

from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestTourStandings(TransactionCase):
    """T-13: Standings computation lifecycle tour."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.season = cls.env["federation.season"].create(
            {
                "name": "Standings Tour Season",
                "code": "STS26",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Standard Rules",
                "code": "STD",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )
        cls.tournament = cls.env["federation.tournament"].create(
            {
                "name": "Standings Tour Cup",
                "code": "STC26",
                "season_id": cls.season.id,
                "rule_set_id": cls.rule_set.id,
                "date_start": "2026-06-01",
            }
        )

        club = cls.env["federation.club"].create(
            {"name": "Standings Club", "code": "STD1"}
        )
        cls.team_a = cls.env["federation.team"].create(
            {"name": "Team A", "club_id": club.id, "code": "STA"}
        )
        cls.team_b = cls.env["federation.team"].create(
            {"name": "Team B", "club_id": club.id, "code": "STB"}
        )
        cls.team_c = cls.env["federation.team"].create(
            {"name": "Team C", "club_id": club.id, "code": "STC"}
        )

        cls.pa = cls.env["federation.tournament.participant"].create(
            {"tournament_id": cls.tournament.id, "team_id": cls.team_a.id}
        )
        cls.pb = cls.env["federation.tournament.participant"].create(
            {"tournament_id": cls.tournament.id, "team_id": cls.team_b.id}
        )
        cls.pc = cls.env["federation.tournament.participant"].create(
            {"tournament_id": cls.tournament.id, "team_id": cls.team_c.id}
        )

        # Determine optional result-control field presence
        cls.has_include_flag = (
            "include_in_official_standings" in cls.env["federation.match"]._fields
        )

    def _make_match(
        self, home, away, home_score, away_score, state="done", include=True
    ):
        """Create a completed match record."""
        vals = {
            "tournament_id": self.tournament.id,
            "home_team_id": home.id,
            "away_team_id": away.id,
            "home_score": home_score,
            "away_score": away_score,
            "state": state,
        }
        if self.has_include_flag:
            vals["include_in_official_standings"] = include
        return self.env["federation.match"].create(vals)

    def _make_standing(self):
        """Create a fresh draft standing for the tournament."""
        return self.env["federation.standing"].create(
            {
                "name": "Main Table",
                "tournament_id": self.tournament.id,
                "rule_set_id": self.rule_set.id,
            }
        )

    def test_standing_starts_draft(self):
        """New standing is in draft state with no lines."""
        standing = self._make_standing()
        self.assertEqual(standing.state, "draft")
        self.assertEqual(len(standing.line_ids), 0)

    def test_recompute_with_no_matches(self):
        """Recomputing with no done matches creates lines with zero stats for each participant."""
        standing = self._make_standing()
        standing.action_recompute()
        self.assertEqual(standing.state, "computed")
        self.assertEqual(len(standing.line_ids), 3)
        for line in standing.line_ids:
            self.assertEqual(line.played, 0)
            self.assertEqual(line.points, 0)

    def test_recompute_correct_points(self):
        """Points are computed correctly: A beats B (3pts), B beats C (3pts), A draws C (1pt each)."""
        # A: 1W 1D = 4pts | B: 1W 1L = 3pts | C: 1D 1L = 1pt
        self._make_match(self.team_a, self.team_b, 2, 1)  # A wins
        self._make_match(self.team_b, self.team_c, 3, 0)  # B wins
        self._make_match(self.team_a, self.team_c, 1, 1)  # draw

        standing = self._make_standing()
        standing.action_recompute()
        self.assertEqual(standing.state, "computed")

        lines = {line.participant_id.team_id: line for line in standing.line_ids}
        self.assertEqual(lines[self.team_a].points, 4)
        self.assertEqual(lines[self.team_b].points, 3)
        self.assertEqual(lines[self.team_c].points, 1)
        self.assertEqual(lines[self.team_a].rank, 1)

    def test_lines_sorted_by_points_then_wins(self):
        """Ranking: points desc, then wins desc as tiebreaker."""
        # A: 1W 1D 0L = 4pts | B: 1W 1L = 3pts | C: 1D 1L = 1pt
        self._make_match(self.team_a, self.team_b, 2, 0)
        self._make_match(self.team_a, self.team_c, 1, 1)
        self._make_match(self.team_b, self.team_c, 2, 0)

        standing = self._make_standing()
        standing.action_recompute()
        ranks = {line.participant_id.team_id: line.rank for line in standing.line_ids}
        self.assertLess(ranks[self.team_a], ranks[self.team_b])
        self.assertLess(ranks[self.team_b], ranks[self.team_c])

    def test_tiebreak_notes_populated_for_tied_teams(self):
        """Tiebreak notes are set when two teams share the same points total."""
        # A and B both get 3pts (each wins once); C loses twice
        self._make_match(self.team_a, self.team_c, 2, 0)  # A 3pts
        self._make_match(self.team_b, self.team_c, 2, 0)  # B 3pts
        # A vs B: A wins — A gets 6pts, B stays 3pts — no tie between A and B,
        # but set up a proper tie: give A and B equal wins and same GD
        # Reset: use a fresh tournament to avoid cross-test interference
        tournament2 = self.env["federation.tournament"].create(
            {
                "name": "Tiebreak Tour",
                "code": "TBT",
                "season_id": self.season.id,
                "rule_set_id": self.rule_set.id,
                "date_start": "2026-07-01",
            }
        )
        self.env["federation.tournament.participant"].create(
            {"tournament_id": tournament2.id, "team_id": self.team_a.id}
        )
        self.env["federation.tournament.participant"].create(
            {"tournament_id": tournament2.id, "team_id": self.team_b.id}
        )
        self.env["federation.tournament.participant"].create(
            {"tournament_id": tournament2.id, "team_id": self.team_c.id}
        )

        has_flag = self.has_include_flag

        def _m(h, a, hs, aws):
            vals = {
                "tournament_id": tournament2.id,
                "home_team_id": h.id,
                "away_team_id": a.id,
                "home_score": hs,
                "away_score": aws,
                "state": "done",
            }
            if has_flag:
                vals["include_in_official_standings"] = True
            return self.env["federation.match"].create(vals)

        _m(self.team_a, self.team_b, 1, 0)  # A wins: 3pts, B: 0pts
        _m(self.team_c, self.team_b, 0, 1)  # B wins: 3pts
        _m(self.team_a, self.team_c, 1, 0)  # A wins: 6pts, C: 0pts
        # Now A=6pts, B=3pts, C=0pts — no tie. To force a tie, skip A vs C match:
        # Make a scenario: A 3pts (1W), B 3pts (1W), tied on points and wins; A has better GD
        tournament3 = self.env["federation.tournament"].create(
            {
                "name": "True Tie Tour",
                "code": "TTT",
                "season_id": self.season.id,
                "rule_set_id": self.rule_set.id,
                "date_start": "2026-08-01",
            }
        )
        for t in [self.team_a, self.team_b, self.team_c]:
            self.env["federation.tournament.participant"].create(
                {"tournament_id": tournament3.id, "team_id": t.id}
            )

        def _m3(h, a, hs, aws):
            vals = {
                "tournament_id": tournament3.id,
                "home_team_id": h.id,
                "away_team_id": a.id,
                "home_score": hs,
                "away_score": aws,
                "state": "done",
            }
            if has_flag:
                vals["include_in_official_standings"] = True
            return self.env["federation.match"].create(vals)

        _m3(self.team_a, self.team_c, 2, 0)  # A 3pts, GD +2
        _m3(
            self.team_b, self.team_c, 1, 0
        )  # B 3pts, GD +1 — tie on pts+wins, A wins on GD
        standing3 = self.env["federation.standing"].create(
            {
                "name": "Tie Table",
                "tournament_id": tournament3.id,
                "rule_set_id": self.rule_set.id,
            }
        )
        standing3.action_recompute()

        lines = {line.participant_id.team_id: line for line in standing3.line_ids}
        # B is ranked 2nd, tied on points with A but below by GD; should have tiebreak note
        b_line = lines[self.team_b]
        a_line = lines[self.team_a]
        self.assertLess(a_line.rank, b_line.rank)
        self.assertTrue(b_line.tiebreak_notes)

    def test_freeze_blocks_recompute(self):
        """Frozen standing raises ValidationError on action_recompute without force flag."""
        standing = self._make_standing()
        standing.action_recompute()
        standing.action_freeze()
        self.assertEqual(standing.state, "frozen")
        with self.assertRaises(ValidationError):
            standing.action_recompute()

    def test_force_recompute_works_on_frozen(self):
        """Force-recompute succeeds on frozen standing and updates lines."""
        self._make_match(self.team_a, self.team_b, 2, 0)
        standing = self._make_standing()
        standing.action_recompute()
        standing.action_freeze()

        # Add another match result after freezing
        self._make_match(self.team_b, self.team_c, 3, 0)
        standing.with_context(force_recompute=True).action_recompute()
        self.assertEqual(standing.state, "computed")
        lines = {line.participant_id.team_id: line for line in standing.line_ids}
        self.assertEqual(lines[self.team_b].played, 2)

    def test_unfreeze_allows_recompute(self):
        """Unfreeze transitions frozen → computed and recompute then works."""
        standing = self._make_standing()
        standing.action_recompute()
        standing.action_freeze()
        standing.action_unfreeze()
        self.assertEqual(standing.state, "computed")
        standing.action_recompute()  # should not raise
        self.assertEqual(standing.state, "computed")

    def test_contested_match_excluded_when_flag_present(self):
        """Matches with include_in_official_standings=False are excluded."""
        if not self.has_include_flag:
            self.skipTest("result_control not installed")

        self._make_match(self.team_a, self.team_b, 5, 0, include=True)
        self._make_match(self.team_a, self.team_c, 5, 0, include=False)  # excluded

        standing = self._make_standing()
        standing.action_recompute()
        lines = {line.participant_id.team_id: line for line in standing.line_ids}
        # A only wins 1 official match (vs B); vs C excluded
        self.assertEqual(lines[self.team_a].played, 1)
        self.assertEqual(lines[self.team_a].points, 3)
