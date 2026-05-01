"""
Tests for tiebreak notes on federation.standing.line (Phase 3).

Coverage:
- Teams with different points: no tiebreak note for lower team
- Teams tied on points but different wins: "Ranked by wins"
- Teams tied on points+wins but different GD: "Ranked by goal difference"
- Teams tied on points+wins+GD but different GF: "Ranked by goals scored"
- Teams fully equal: "Ranked alphabetically by team name"
- Rank 1 always gets empty tiebreak_notes
"""

from odoo.tests.common import TransactionCase


class TestTiebreakNotes(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Set up shared test data for the test case."""
        super().setUpClass()
        cls.club = cls.env["federation.club"].create(
            {
                "name": "TB Club",
                "code": "TBC",
            }
        )
        cls.season = cls.env["federation.season"].create(
            {
                "name": "TB Season",
                "code": "TBS24",
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
            }
        )
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "TB Rule Set",
                "code": "TBRS",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_setup(self, suffix):
        """Create tournament + 2 participants, return (tournament, p1, p2)."""
        t1 = self.env["federation.team"].create(
            {
                "name": f"Alpha {suffix}",
                "club_id": self.club.id,
                "code": f"AL{suffix}",
            }
        )
        t2 = self.env["federation.team"].create(
            {
                "name": f"Zeta {suffix}",
                "club_id": self.club.id,
                "code": f"ZT{suffix}",
            }
        )
        tour = self.env["federation.tournament"].create(
            {
                "name": f"TB Tour {suffix}",
                "code": f"TBT{suffix}",
                "season_id": self.season.id,
                "date_start": "2024-06-01",
                "rule_set_id": self.rule_set.id,
            }
        )
        p1 = self.env["federation.tournament.participant"].create(
            {
                "tournament_id": tour.id,
                "team_id": t1.id,
            }
        )
        p2 = self.env["federation.tournament.participant"].create(
            {
                "tournament_id": tour.id,
                "team_id": t2.id,
            }
        )
        return tour, t1, t2, p1, p2

    def _make_match(self, tour, home, away, home_score, away_score, state="done"):
        """Exercise make match."""
        vals = {
            "tournament_id": tour.id,
            "home_team_id": home.id,
            "away_team_id": away.id,
            "home_score": home_score,
            "away_score": away_score,
            "state": state,
        }
        if "include_in_official_standings" in self.env["federation.match"]._fields:
            vals["include_in_official_standings"] = True
        return self.env["federation.match"].create(vals)

    def _standing(self, tour):
        """Exercise standing."""
        return self.env["federation.standing"].create(
            {
                "name": f"Standing {tour.name}",
                "tournament_id": tour.id,
                "rule_set_id": self.rule_set.id,
            }
        )

    def _lines_by_team(self, standing):
        """Return dict {team.name: standing_line}."""
        return {line.team_id.name: line for line in standing.line_ids}

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------

    def test_rank1_has_no_tiebreak_note(self):
        """The rank-1 line always has an empty tiebreak_notes."""
        tour, t1, t2, p1, p2 = self._make_setup("R1")
        self._make_match(tour, t1, t2, 3, 0)  # Alpha wins
        s = self._standing(tour)
        s.action_recompute()
        lines = self._lines_by_team(s)
        self.assertEqual(lines[t1.name].rank, 1)
        self.assertFalse(lines[t1.name].tiebreak_notes)

    def test_no_tiebreak_when_separated_by_points(self):
        """Rank-2 gets empty note when separated from rank-1 by points."""
        tour, t1, t2, p1, p2 = self._make_setup("NOBR")
        self._make_match(tour, t1, t2, 1, 0)  # Alpha wins (3 pts vs 0)
        s = self._standing(tour)
        s.action_recompute()
        lines = self._lines_by_team(s)
        self.assertEqual(lines[t2.name].rank, 2)
        self.assertFalse(lines[t2.name].tiebreak_notes)

    def test_tiebreak_by_wins(self):
        """Teams equal on points but different wins → 'Ranked by wins'."""
        tour, t1, t2, p1, p2 = self._make_setup("WIN")
        # Both get 3 points: Alpha wins one match (3 pts), Zeta draws two (1+1=2)
        # Need equal points: both win 1 draw 1 → 4 pts? Let's do both win once, draw once
        # Alpha: 3 pts (1W, 0D, 1L)  — wait, let's use 3 teams method via inject
        # Simple: inject stats directly through matches that result in same points diff wins
        # Alpha wins 1 match (3 pts, 1 win), Zeta draws 3 matches? No — only 2 teams.

        # With two teams: only W/D/L between them.
        # Both get draw → 1 pt each, 0 wins each, same GD → alphabetical
        # To test "wins" tiebreak need 3 teams. Use setUpClass teams...
        # Let's add a third team:
        t3 = self.env["federation.team"].create(
            {
                "name": "Beta WIN",
                "club_id": self.club.id,
                "code": "BWIN",
            }
        )
        p3 = self.env["federation.tournament.participant"].create(
            {
                "tournament_id": tour.id,
                "team_id": t3.id,
            }
        )
        # Alpha beats Beta 1-0 (3 pts), Zeta beats Beta 1-0 (3 pts)
        # Alpha vs Zeta draw 0-0 (each +1 pt) → Alpha=4, Zeta=4, Beta=0
        # Alpha: 2W(vs Beta + draw... no)
        # Let's go:
        # Alpha beats Beta 1-0 → Alpha 3pts, Beta 0pts
        # Zeta draws Alpha 0-0 → Alpha 4pts(1W,1D), Zeta 1pt(0W,1D)
        # That's not equal points. Let me try:
        # Both Alpha and Zeta beat Beta: Alpha 3pts, Zeta 3pts, Beta 0
        # Alpha vs Zeta is a draw: Alpha 4pts(1W,1D), Zeta 4pts(1W,1D) → equal wins too
        # Hmm, need different wins with same total points. With 3 teams:
        # Alpha beats Zeta (3pts), Alpha draws Beta (1pt) → Alpha=4pts, 1W 1D
        # Zeta draws Beta (1pt), Zeta loses Alpha (0pt) → Zeta=1pt
        # That doesn't work. Let me try:
        # Alpha: 2 draws (2pts, 0 wins), Zeta: 1 win 1 loss (3 pts, 1 win)... different points
        # The only way same points, different wins with 3 teams round robin:
        # Alpha beats Beta (3pts), Zeta draws Alpha (1pt each), Zeta beats Beta (3pts)
        # Alpha total: 3 + 1 = 4, Zeta total: 1 + 3 = 4 — BUT Alpha 1W1D, Zeta 1W1D → same wins
        # Let's try: separate matches:
        # Alpha 3W (9pts) vs Zeta 3D (3pts) — different points

        # The simplest is: reset and inject lines manually via internal helper.
        # Actually, check_tiebreak_notes is tested internally; let's test _compute_tiebreak_notes
        # directly with synthetic data.
        s = self._standing(tour)
        participant_map = {p.id: p for p in tour.participant_ids}
        # Synthetic sorted_items: (pid, stats) — Alpha has 1 win, Zeta has 0 wins, same points
        sorted_items = [
            (p1.id, {"points": 4, "won": 2, "score_for": 4, "score_against": 2}),
            (p3.id, {"points": 4, "won": 1, "score_for": 3, "score_against": 3}),
            (p2.id, {"points": 4, "won": 0, "score_for": 2, "score_against": 4}),
        ]
        notes = s._compute_tiebreak_notes(sorted_items, participant_map)
        self.assertEqual(notes[p1.id], "")
        self.assertIn("wins", notes[p3.id].lower())
        self.assertIn("wins", notes[p2.id].lower())

    def test_tiebreak_by_goal_difference(self):
        """Teams equal on points and wins but differ on GD → 'Ranked by goal difference'."""
        tour, t1, t2, p1, p2 = self._make_setup("GD")
        s = self._standing(tour)
        participant_map = {}
        sorted_items = [
            (p1.id, {"points": 3, "won": 1, "score_for": 3, "score_against": 0}),
            (p2.id, {"points": 3, "won": 1, "score_for": 2, "score_against": 1}),
        ]
        notes = s._compute_tiebreak_notes(sorted_items, participant_map)
        self.assertEqual(notes[p1.id], "")
        self.assertIn("goal difference", notes[p2.id].lower())

    def test_tiebreak_by_goals_scored(self):
        """Teams equal on points, wins, GD but differ on GF → 'Ranked by goals scored'."""
        tour, t1, t2, p1, p2 = self._make_setup("GF")
        s = self._standing(tour)
        participant_map = {}
        sorted_items = [
            (p1.id, {"points": 3, "won": 1, "score_for": 5, "score_against": 2}),
            (p2.id, {"points": 3, "won": 1, "score_for": 3, "score_against": 0}),
        ]
        notes = s._compute_tiebreak_notes(sorted_items, participant_map)
        self.assertEqual(notes[p1.id], "")
        self.assertIn("goals scored", notes[p2.id].lower())

    def test_tiebreak_alphabetical(self):
        """Teams fully equal in all metrics → 'Ranked alphabetically by team name'."""
        tour, t1, t2, p1, p2 = self._make_setup("ALPHA")
        s = self._standing(tour)
        participant_map = {}
        sorted_items = [
            (p1.id, {"points": 3, "won": 1, "score_for": 2, "score_against": 1}),
            (p2.id, {"points": 3, "won": 1, "score_for": 2, "score_against": 1}),
        ]
        notes = s._compute_tiebreak_notes(sorted_items, participant_map)
        self.assertEqual(notes[p1.id], "")
        self.assertIn("alphabetically", notes[p2.id].lower())

    def test_tiebreak_stored_on_line_after_recompute(self):
        """After action_recompute, tiebreak_notes are stored on the lines."""
        tour, t1, t2, p1, p2 = self._make_setup("STORE")
        # Draw: equal points, equal wins (0), equal GD, equal GF → alphabetical
        self._make_match(tour, t1, t2, 1, 1)
        s = self._standing(tour)
        s.action_recompute()
        lines = self._lines_by_team(s)
        # Alpha comes first alphabetically, Zeta second
        rank1_name = sorted([t1.name, t2.name])[0]
        rank2_name = sorted([t1.name, t2.name])[1]
        self.assertEqual(lines[rank1_name].tiebreak_notes or "", "")
        self.assertIn(
            "alphabetically", (lines[rank2_name].tiebreak_notes or "").lower()
        )
