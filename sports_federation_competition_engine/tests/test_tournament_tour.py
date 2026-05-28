"""
Tour: Full Tournament Workflow — 9 teams, Round-Robin → Knockout.

This integration test is the canonical CI "tour" for the tournament lifecycle.
It exercises every major step an administrator takes, in order:

  1.  Setup         — rule set, competition, season, clubs, teams
  2.  Tournament    — create, configure, open
  3.  Stages        — round-robin group stage + knockout stage
  4.  Participants  — 9 confirmed participants assigned to the group
  5.  RR schedule   — generate (9 teams = 8 rounds, 4 matches + 1 bye per round)
  6.  RR execution  — score and finish all 36 matches
  7.  Standings     — compute and freeze the group-stage standing
  8.  Progression   — advance the top 8 teams to the knockout stage
  9.  KO schedule   — generate the 8-team bracket (3 rounds, 7 matches)
  10. KO execution  — score and finish every bracket match
  11. Completion    — verify the champion and close the tournament

Key invariants verified throughout:
  - match counts after schedule generation
  - all RR matches reach state "done"
  - standings state becomes "computed" then "frozen"
  - exactly 8 participants appear in the knockout stage
  - knockout produces a single undisputed champion
  - tournament closes cleanly
"""

from odoo.tests.common import TransactionCase


class TestTournamentTour(TransactionCase):
    """Full 9-team Round-Robin → Knockout tournament tour."""

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # ----- Rule set -----------------------------------------------
        cls.rule_set = cls.env["federation.rule.set"].create(
            {
                "name": "Tour Rule Set",
                "code": "TRS",
                "points_win": 3,
                "points_draw": 1,
                "points_loss": 0,
            }
        )

        # ----- Season -------------------------------------------------
        cls.season = cls.env["federation.season"].create(
            {
                "name": "Tour Season 2026",
                "code": "TOUR2026",
                "date_start": "2026-01-01",
                "date_end": "2026-12-31",
            }
        )

        # ----- Competition --------------------------------------------
        cls.competition = cls.env["federation.competition"].create(
            {
                "name": "Tour Championship",
                "code": "TOUR",
                "rule_set_id": cls.rule_set.id,
            }
        )
        cls.competition.action_activate()

        # ----- Competition edition (links competition to season) -------
        cls.edition = cls.env["federation.competition.edition"].create(
            {
                "competition_id": cls.competition.id,
                "season_id": cls.season.id,
                "name": "Tour Championship 2026",
            }
        )

        # ----- 9 clubs + 9 teams (one per club) -----------------------
        cls.clubs = cls.env["federation.club"]
        cls.teams = cls.env["federation.team"]
        for i in range(1, 10):
            club = cls.env["federation.club"].create(
                {
                    "name": f"Tour Club {i:02d}",
                    "code": f"TC{i:02d}",
                }
            )
            cls.clubs |= club
            team = cls.env["federation.team"].create(
                {
                    "name": f"Tour Team {i:02d}",
                    "code": f"TT{i:02d}",
                    "club_id": club.id,
                    "gender": "male",
                }
            )
            cls.teams |= team

    # ------------------------------------------------------------------
    # Helper: deterministic score that avoids draws
    # ------------------------------------------------------------------

    @staticmethod
    def _score(idx):
        """Return (home, away) — always a decisive result."""
        h = (idx % 5) + 1
        a = idx % 4
        if h == a:
            a = max(0, a - 1)
        return h, a

    def _ensure_ready_roster(self, team, season):
        """Guarantee an active roster exists so schedule guards pass."""
        roster = self.env["federation.team.roster"].search(
            [("team_id", "=", team.id), ("season_id", "=", season.id)],
            limit=1,
        )
        if not roster:
            roster = self.env["federation.team.roster"].create(
                {
                    "team_id": team.id,
                    "season_id": season.id,
                }
            )

        active_line_count = self.env["federation.team.roster.line"].search_count(
            [("roster_id", "=", roster.id), ("status", "=", "active")]
        )
        if not active_line_count:
            player = self.env["federation.player"].create(
                {
                    "first_name": f"Tour{team.id}",
                    "last_name": "Roster",
                    "gender": "male",
                    "club_id": team.club_id.id,
                }
            )
            self.env["federation.team.roster.line"].create(
                {
                    "roster_id": roster.id,
                    "player_id": player.id,
                    "status": "active",
                }
            )

        if roster.status != "active":
            roster.action_activate()

        return roster

    # ------------------------------------------------------------------
    # Tour
    # ------------------------------------------------------------------

    def test_full_tournament_tour_9_teams(self):
        """Walk the complete 9-team round-robin → knockout workflow."""

        # =================================================================
        # STEP 1: Create and open the tournament
        # =================================================================
        tournament = self.env["federation.tournament"].create(
            {
                "name": "Tour Cup 2026",
                "code": "TCUP26",
                "season_id": self.season.id,
                "edition_id": self.edition.id,
                "rule_set_id": self.rule_set.id,
                "date_start": "2026-03-01",
                "date_end": "2026-05-31",
                "gender": "male",
                "tournament_type": "multi_day",
            }
        )
        self.assertEqual(tournament.state, "draft")
        tournament.action_open()
        self.assertEqual(tournament.state, "open")

        # =================================================================
        # STEP 2: Create stages (required before action_start)
        # =================================================================
        stage_rr = self.env["federation.tournament.stage"].create(
            {
                "name": "Group Stage",
                "tournament_id": tournament.id,
                "sequence": 10,
                "stage_type": "group",
            }
        )
        stage_ko = self.env["federation.tournament.stage"].create(
            {
                "name": "Knockout Stage",
                "tournament_id": tournament.id,
                "sequence": 20,
                "stage_type": "knockout",
            }
        )

        # Start the tournament (open → in_progress); stages must exist first
        tournament.action_start()
        self.assertEqual(tournament.state, "in_progress")

        # =================================================================
        # STEP 3: Create one group for the round-robin stage
        # =================================================================
        group = self.env["federation.tournament.group"].create(
            {
                "name": "Pool A",
                "stage_id": stage_rr.id,
                "sequence": 1,
                "max_participants": 9,
            }
        )

        # =================================================================
        # STEP 4: Enrol and confirm 9 participants
        # =================================================================
        participants = self.env["federation.tournament.participant"]
        for idx, team in enumerate(self.teams, start=1):
            p = self.env["federation.tournament.participant"].create(
                {
                    "tournament_id": tournament.id,
                    "team_id": team.id,
                    "stage_id": stage_rr.id,
                    "group_id": group.id,
                    "state": "confirmed",
                    "seed": idx,
                }
            )
            participants |= p

        self.assertEqual(len(participants), 9)
        self.assertTrue(all(p.state == "confirmed" for p in participants))

        # =================================================================
        # STEP 5: Generate RR schedule
        # =================================================================
        # Tournament is already in_progress (action_start called above)

        # 9 teams (odd) → 8 rounds, 4 matches per round, 1 bye per round = 36 matches
        expected_rr_matches = 36  # C(9,2) = 36

        # Pre-create enough rounds (9 − 1 = 8 rounds for single cycle)
        for i in range(1, 9):
            self.env["federation.tournament.round"].create(
                {
                    "stage_id": stage_rr.id,
                    "group_id": group.id,
                    "sequence": i,
                    "name": f"Round {i}",
                }
            )

        rr_service = self.env["federation.round.robin.service"]
        rr_options = {
            "double_round": False,
            "schedule_by_round": True,
            "round_interval_hours": 24,
            "start_datetime": "2026-03-07 10:00:00",
            "interval_hours": 2,
            "group": group,
            "overwrite": False,
            "full_cycles": 1,
        }
        rr_matches_raw = rr_service.generate(tournament, stage_rr, participants, rr_options)
        # Service may return a list or a recordset; normalise to ORM recordset.
        if isinstance(rr_matches_raw, list):
            rr_match_ids = [m.id for m in rr_matches_raw]
            rr_matches = self.env["federation.match"].browse(rr_match_ids)
        else:
            rr_matches = rr_matches_raw

        self.assertEqual(
            len(rr_matches),
            expected_rr_matches,
            f"Expected {expected_rr_matches} RR matches for 9 teams, got {len(rr_matches)}",
        )

        # =================================================================
        # STEP 6: Execute all round-robin matches
        # =================================================================
        for idx, match in enumerate(rr_matches):
            match.action_schedule()
            home_score, away_score = self._score(idx)
            match.write({"home_score": home_score, "away_score": away_score})
            match.action_done()

        done_rr = rr_matches.filtered(lambda m: m.state == "done")
        self.assertEqual(
            len(done_rr),
            expected_rr_matches,
            "Not all RR matches reached state 'done'",
        )

        # =================================================================
        # STEP 7: Compute and freeze the group-stage standing
        # =================================================================
        standing = self.env["federation.standing"].create(
            {
                "name": "Group Stage Standing",
                "tournament_id": tournament.id,
                "stage_id": stage_rr.id,
                "group_id": group.id,
                "rule_set_id": self.rule_set.id,
            }
        )
        standing.action_recompute()
        self.assertEqual(standing.state, "computed")
        self.assertEqual(
            len(standing.line_ids),
            9,
            "Standing should have one line per team",
        )

        # Verify the ranking is complete (all ranks 1–9 assigned)
        ranks = sorted(standing.line_ids.mapped("rank"))
        self.assertEqual(ranks, list(range(1, 10)))

        standing.action_freeze()
        self.assertEqual(standing.state, "frozen")

        # =================================================================
        # STEP 8: Progress top 8 teams to the knockout stage
        # =================================================================
        progression = self.env["federation.stage.progression"].create(
            {
                "tournament_id": tournament.id,
                "source_stage_id": stage_rr.id,
                "source_group_id": group.id,
                "target_stage_id": stage_ko.id,
                "rank_from": 1,
                "rank_to": 8,
                "seeding_method": "keep_rank",
                "auto_advance": False,
            }
        )
        progression.action_execute()

        ko_participants = self.env["federation.tournament.participant"].search(
            [
                ("tournament_id", "=", tournament.id),
                ("stage_id", "=", stage_ko.id),
                ("state", "=", "confirmed"),
            ]
        )
        self.assertEqual(
            len(ko_participants),
            8,
            f"Expected 8 teams in knockout stage, got {len(ko_participants)}",
        )

        # =================================================================
        # STEP 9: Generate the knockout bracket (8 teams → 7 matches, 3 rounds)
        # =================================================================
        ko_service = self.env["federation.knockout.service"]
        ko_options = {
            "start_datetime": "2026-05-03 10:00:00",
            "interval_hours": 2,
            "bracket_size": "power_of_two",
            "seeding": "seed",
            "overwrite": False,
        }
        ko_matches_raw = ko_service.generate(tournament, stage_ko, ko_participants, ko_options)
        if isinstance(ko_matches_raw, list):
            ko_matches = self.env["federation.match"].browse([m.id for m in ko_matches_raw])
        else:
            ko_matches = ko_matches_raw

        # 8 teams → 4 QF + 2 SF + 1 Final = 7 matches
        self.assertEqual(
            len(ko_matches),
            7,
            f"Expected 7 KO matches for 8 teams, got {len(ko_matches)}",
        )

        # =================================================================
        # STEP 10: Execute the knockout bracket round by round
        # =================================================================
        all_ko_matches = self.env["federation.match"].search(
            [("stage_id", "=", stage_ko.id)],
            order="round_number asc, bracket_position asc",
        )
        max_round = max(all_ko_matches.mapped("round_number") or [1])

        for rnd in range(1, max_round + 1):
            round_matches = all_ko_matches.filtered(lambda m: m.round_number == rnd)
            for idx, match in enumerate(round_matches):
                if not match.home_team_id or not match.away_team_id:
                    # Placeholder: bye or not yet filled by previous round
                    continue
                match.action_schedule()
                home_score, away_score = self._score(rnd * 10 + idx)
                match.write({"home_score": home_score, "away_score": away_score})
                match.action_done()

        # All non-placeholder knockout matches must be done
        played_ko = all_ko_matches.filtered(
            lambda m: m.home_team_id and m.away_team_id and m.state == "done"
        )
        self.assertEqual(len(played_ko), 7, "Not all knockout matches reached 'done'")

        # =================================================================
        # STEP 11: Verify champion and close the tournament
        # =================================================================
        final = all_ko_matches.filtered(lambda m: m.round_number == max_round)
        self.assertEqual(len(final), 1, "There must be exactly one Final match")
        final = final[0]
        self.assertNotEqual(
            final.home_score,
            final.away_score,
            "The Final must have a decisive result (no draw allowed in KO)",
        )
        champion = (
            final.home_team_id
            if final.home_score > final.away_score
            else final.away_team_id
        )
        self.assertTrue(champion, "A champion must emerge from the Final")

        # Close the tournament
        tournament.action_close()
        self.assertEqual(
            tournament.state,
            "closed",
            "Tournament should reach 'closed' state after completion",
        )

    def test_participant_withdrawal_reduces_schedule_scope(self):
        """
        Withdrawal tour: confirm 5 participants, withdraw 1 before schedule
        generation, verify only 4 active teams' matches are generated.

        Invariants:
          - withdrawn participant has state 'withdrawn'
          - RR schedule for 4 active teams = C(4,2) = 6 matches
          - withdrawn team appears in 0 matches
        """
        # --- tournament setup -------------------------------------------
        tournament = self.env["federation.tournament"].create(
            {
                "name": "Withdrawal Tour 2026",
                "code": "WTOUR26",
                "season_id": self.season.id,
                "date_start": "2026-04-01",
                "date_end": "2026-04-30",
                "tournament_type": "multi_day",
            }
        )
        tournament.action_open()

        stage = self.env["federation.tournament.stage"].create(
            {
                "name": "Group Stage",
                "tournament_id": tournament.id,
                "stage_type": "group",
            }
        )
        tournament.action_start()

        group = self.env["federation.tournament.group"].create(
            {
                "name": "Pool A",
                "stage_id": stage.id,
            }
        )

        # Enrol 5 participants (first 5 teams from the shared pool)
        five_teams = self.teams[:5]
        participants = self.env["federation.tournament.participant"]
        for idx, team in enumerate(five_teams, start=1):
            p = self.env["federation.tournament.participant"].create(
                {
                    "tournament_id": tournament.id,
                    "team_id": team.id,
                    "stage_id": stage.id,
                    "group_id": group.id,
                    "state": "confirmed",
                    "seed": idx,
                }
            )
            participants |= p

        # --- withdraw the last participant -------------------------------
        withdrawn_participant = participants[-1]
        withdrawn_team = withdrawn_participant.team_id
        withdrawn_participant.action_withdraw()
        self.assertEqual(withdrawn_participant.state, "withdrawn")

        # Only 4 active participants remain
        active_participants = participants.filtered(lambda p: p.state == "confirmed")
        self.assertEqual(len(active_participants), 4)

        # --- generate RR schedule for active participants only ----------
        # 4 teams (even): 3 rounds, 2 matches per round = 6 matches
        for i in range(1, 4):
            self.env["federation.tournament.round"].create(
                {
                    "stage_id": stage.id,
                    "group_id": group.id,
                    "sequence": i,
                    "name": f"Round {i}",
                }
            )

        rr_service = self.env["federation.round.robin.service"]
        rr_options = {
            "double_round": False,
            "schedule_by_round": True,
            "round_interval_hours": 24,
            "start_datetime": "2026-04-05 10:00:00",
            "interval_hours": 2,
            "group": group,
            "overwrite": False,
        }
        rr_raw = rr_service.generate(tournament, stage, active_participants, rr_options)
        if isinstance(rr_raw, list):
            rr_matches = self.env["federation.match"].browse([m.id for m in rr_raw])
        else:
            rr_matches = rr_raw

        self.assertEqual(
            len(rr_matches),
            6,
            f"Expected C(4,2)=6 matches for 4 active teams, got {len(rr_matches)}",
        )

        # Withdrawn team participates in zero matches
        team_ids_in_schedule = set(
            rr_matches.mapped("home_team_id.id")
            + rr_matches.mapped("away_team_id.id")
        )
        self.assertNotIn(
            withdrawn_team.id,
            team_ids_in_schedule,
            "The withdrawn team must not appear in any scheduled match",
        )

        # --- close tournament ------------------------------------------
        for idx, match in enumerate(rr_matches):
            match.action_schedule()
            h, a = self._score(idx)
            match.write({"home_score": h, "away_score": a})
            match.action_done()

        tournament.action_close()
        self.assertEqual(tournament.state, "closed")

    def test_knockout_only_tournament(self):
        """
        KO-only tour: 8 teams enter a straight knockout bracket with no
        preceding group stage.

        Invariants:
          - bracket generates exactly 7 matches across 3 rounds
          - every match is played and reaches state 'done'
          - a unique champion emerges from the final
          - tournament closes from in_progress state
        """
        # --- tournament setup -------------------------------------------
        tournament = self.env["federation.tournament"].create(
            {
                "name": "KO Cup 2026",
                "code": "KOCUP26",
                "season_id": self.season.id,
                "date_start": "2026-06-01",
                "date_end": "2026-06-15",
                "tournament_type": "multi_day",
            }
        )
        tournament.action_open()

        stage = self.env["federation.tournament.stage"].create(
            {
                "name": "Knockout",
                "tournament_id": tournament.id,
                "stage_type": "knockout",
            }
        )
        tournament.action_start()
        self.assertEqual(tournament.state, "in_progress")

        # --- 8 confirmed participants (seeded 1-8) ----------------------
        eight_teams = self.teams[:8]
        participants = self.env["federation.tournament.participant"]
        for idx, team in enumerate(eight_teams, start=1):
            p = self.env["federation.tournament.participant"].create(
                {
                    "tournament_id": tournament.id,
                    "team_id": team.id,
                    "stage_id": stage.id,
                    "state": "confirmed",
                    "seed": idx,
                }
            )
            participants |= p

        self.assertEqual(len(participants), 8)

        for team in eight_teams:
            self._ensure_ready_roster(team, self.season)

        # --- generate knockout bracket ----------------------------------
        ko_service = self.env["federation.knockout.service"]
        ko_options = {
            "start_datetime": "2026-06-01 10:00:00",
            "interval_hours": 2,
            "bracket_size": "power_of_two",
            "seeding": "seed",
            "overwrite": False,
        }
        ko_raw = ko_service.generate(tournament, stage, participants, ko_options)
        if isinstance(ko_raw, list):
            ko_matches = self.env["federation.match"].browse([m.id for m in ko_raw])
        else:
            ko_matches = ko_raw

        # 8 teams → 4 QF + 2 SF + 1 Final = 7 matches
        self.assertEqual(
            len(ko_matches),
            7,
            f"Expected 7 KO matches for 8 teams, got {len(ko_matches)}",
        )

        # Verify 3 distinct rounds exist
        round_numbers = sorted(set(ko_matches.mapped("round_number")))
        self.assertEqual(len(round_numbers), 3, "8-team KO should span exactly 3 rounds")

        # --- play bracket round by round --------------------------------
        all_matches = self.env["federation.match"].search(
            [("stage_id", "=", stage.id)],
            order="round_number asc, bracket_position asc",
        )
        max_round = max(all_matches.mapped("round_number") or [1])

        for rnd in range(1, max_round + 1):
            round_matches = all_matches.filtered(lambda m: m.round_number == rnd)
            for idx, match in enumerate(round_matches):
                if not match.home_team_id or not match.away_team_id:
                    continue  # placeholder
                match.action_schedule()
                h, a = self._score(rnd * 10 + idx)
                match.write({"home_score": h, "away_score": a})
                match.action_done()

        played = all_matches.filtered(
            lambda m: m.home_team_id and m.away_team_id and m.state == "done"
        )
        self.assertEqual(len(played), 7)

        # --- verify champion -------------------------------------------
        final_match = all_matches.filtered(lambda m: m.round_number == max_round)
        self.assertEqual(len(final_match), 1)
        final_match = final_match[0]
        self.assertNotEqual(final_match.home_score, final_match.away_score)

        champion = (
            final_match.home_team_id
            if final_match.home_score > final_match.away_score
            else final_match.away_team_id
        )
        self.assertIn(
            champion,
            eight_teams,
            "Champion must be one of the 8 entered teams",
        )

        # --- close tournament ------------------------------------------
        tournament.action_close()
        self.assertEqual(tournament.state, "closed")
