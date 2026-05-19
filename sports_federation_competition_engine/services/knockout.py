import logging
import math
import random
from datetime import datetime, timedelta

from odoo import fields, models  # noqa: F401 — _ kept for import compatibility
from odoo.exceptions import UserError  # noqa: F401 — kept for import compatibility

from odoo.addons.sports_federation_tournament.workflow_states import MATCH_STATE_DRAFT

_logger = logging.getLogger(__name__)


class KnockoutService(models.AbstractModel):
    _name = "federation.knockout.service"
    _inherit = "federation.base.schedule.service"
    _description = "Knockout Bracket Generation Service"

    def generate(self, tournament, stage, participants, options):
        """
        Generate a full knockout bracket with all rounds.

        Creates first-round matches with teams assigned, and subsequent-round
        placeholder matches linked via source_match_1_id / source_match_2_id.
        When a match result is entered, teams auto-advance through the bracket.
        """
        self._validate_inputs(tournament, stage, participants, options)

        if options.get("overwrite"):
            self._clear_existing_matches(stage)
        else:
            self._check_existing_matches(stage)

        teams = self._apply_seeding(
            participants, options.get("seeding", "seed"), seed=options.get("seed")
        )
        bracket_size = self._determine_bracket_size(
            len(teams), options.get("bracket_size", "natural")
        )
        first_round_pairs = self._build_first_round(teams, bracket_size)
        bracket_type = options.get("bracket_type", "winners")

        all_matches = self._create_full_bracket(
            tournament,
            stage,
            teams,
            bracket_size,
            first_round_pairs,
            options,
            bracket_type,
        )

        _logger.info(
            "Generated %d knockout matches (%d rounds) for tournament %s, stage %s",
            len(all_matches),
            math.ceil(math.log2(bracket_size)) if bracket_size > 1 else 1,
            tournament.name,
            stage.name,
        )
        return all_matches

    def _validate_inputs(self, tournament, stage, participants, options):
        """Validate inputs."""
        self._validate_tournament_state(tournament)
        self._validate_participant_count(participants)

    def _apply_seeding(self, participants, seeding, seed=None):
        """Apply seeding."""
        if seeding == "random":
            teams = [p.team_id for p in participants]
            if seed is not None:
                random.seed(seed)
            random.shuffle(teams)
            return teams
        elif seeding == "seed":
            sorted_p = sorted(participants, key=lambda p: p.seed or 999)
            return [p.team_id for p in sorted_p]
        else:
            return [p.team_id for p in participants]

    def _determine_bracket_size(self, count, mode):
        """Handle determine bracket size."""
        if mode == "power_of_two":
            return 2 ** math.ceil(math.log2(count))
        return count

    def _build_first_round(self, teams, bracket_size):
        """Build first round."""
        n_actual = len(teams)

        if n_actual >= bracket_size:
            half = bracket_size // 2
            pairs = []
            for i in range(half):
                pairs.append((teams[i], teams[bracket_size - 1 - i]))
            return pairs

        bye_count = bracket_size - n_actual
        teams_playing = teams[bye_count:]
        n_playing = len(teams_playing)
        half = n_playing // 2

        pairs = []
        for i in range(half):
            home = teams_playing[i]
            away = teams_playing[n_playing - 1 - i]
            pairs.append((home, away))

        return pairs

    def _build_round_sources(self, teams, bracket_size, round_1_matches):
        """Build ordered sources for the next round after round 1.

        When the bracket uses power-of-two expansion, top seeds receive byes and
        should be paired against play-in winners in bracket order. Interleave the
        bye entrants with the created round-1 matches so later rounds can be
        wired without indexing past the available play-in matches.
        """
        bye_count = bracket_size - len(teams)
        if bye_count <= 0:
            return [
                {"type": "match", "match": match, "result": "winner"}
                for match in round_1_matches
            ]

        bye_sources = [{"type": "bye", "team": team} for team in teams[:bye_count]]
        match_sources = [
            {"type": "match", "match": match, "result": "winner"}
            for match in round_1_matches
        ]

        round_sources = []
        max_sources = max(len(bye_sources), len(match_sources))
        for idx in range(max_sources):
            if idx < len(bye_sources):
                round_sources.append(bye_sources[idx])
            if idx < len(match_sources):
                round_sources.append(match_sources[idx])

        return round_sources

    def _create_full_bracket(
        self,
        tournament,
        stage,
        teams,
        bracket_size,
        first_round_pairs,
        options,
        bracket_type,
    ):
        """Build the entire bracket: round 1 matches + placeholder matches for subsequent rounds."""
        Match = self.env["federation.match"]
        Round = self.env["federation.tournament.round"]
        start_dt = options.get("start_datetime")
        interval = options.get("interval_hours", 0)
        venue = options.get("venue", "")
        Venue = self.env.get("federation.venue")
        venue_rec = None
        if venue and Venue is not None:
            venue_rec = Venue.search([("name", "=", venue)], limit=1)

        total_rounds = math.ceil(math.log2(bracket_size)) if bracket_size > 1 else 1

        round_names = self._get_round_names(total_rounds)

        # --- Round 1: real matches ---
        round_1_matches = []
        round_1_base = fields.Datetime.to_datetime(start_dt) if start_dt else False
        round_1_vals = {"name": round_names[1]}
        if round_1_base:
            round_1_vals["round_date"] = round_1_base.date()
        if venue_rec and "venue_id" in Round._fields:
            round_1_vals["venue_id"] = venue_rec.id
        round_1_record = Round.get_or_create_stage_round(stage, 1, values=round_1_vals)
        if round_1_record.round_date and round_1_base:
            round_1_base = datetime.combine(
                round_1_record.round_date, round_1_base.time()
            )
        for i, (home, away) in enumerate(first_round_pairs):
            vals = {
                "tournament_id": tournament.id,
                "stage_id": stage.id,
                "home_team_id": home.id,
                "away_team_id": away.id,
                "state": MATCH_STATE_DRAFT,
                "round_id": round_1_record.id,
                "round_number": 1,
                "bracket_position": i + 1,
                "bracket_type": bracket_type,
            }
            if venue_rec and Venue is not None:
                vals["venue_id"] = (
                    round_1_record.venue_id.id
                    if "venue_id" in round_1_record._fields and round_1_record.venue_id
                    else venue_rec.id
                )
            if round_1_base:
                vals["date_scheduled"] = round_1_base + timedelta(hours=i * interval)
            round_1_matches.append(Match.create(vals))

        all_matches = list(round_1_matches)
        feed_sources = self._build_round_sources(teams, bracket_size, round_1_matches)

        # --- Rounds 2..N: placeholder matches ---
        prev_round_sources = feed_sources
        for rnd in range(2, total_rounds + 1):
            matches_in_round = len(prev_round_sources) // 2
            current_matches = []
            round_dt = (
                fields.Datetime.to_datetime(start_dt) + timedelta(hours=(rnd - 1) * 24)
                if start_dt
                else None
            )
            round_vals = {"name": round_names[rnd]}
            if round_dt:
                round_vals["round_date"] = round_dt.date()
            if venue_rec and "venue_id" in Round._fields:
                round_vals["venue_id"] = venue_rec.id
            round_record = Round.get_or_create_stage_round(
                stage, rnd, values=round_vals
            )
            if round_record.round_date and round_dt:
                round_dt = datetime.combine(round_record.round_date, round_dt.time())

            for m in range(matches_in_round):
                src_a = prev_round_sources[m * 2]
                src_b = prev_round_sources[m * 2 + 1]

                vals = {
                    "tournament_id": tournament.id,
                    "stage_id": stage.id,
                    "state": MATCH_STATE_DRAFT,
                    "round_id": round_record.id,
                    "round_number": rnd,
                    "bracket_position": m + 1,
                    "bracket_type": bracket_type,
                }
                if venue_rec and Venue is not None:
                    vals["venue_id"] = (
                        round_record.venue_id.id
                        if "venue_id" in round_record._fields and round_record.venue_id
                        else venue_rec.id
                    )
                if round_dt:
                    vals["date_scheduled"] = round_dt + timedelta(hours=m * interval)

                # Wire source A → home
                if src_a["type"] == "bye":
                    vals["home_team_id"] = src_a["team"].id
                else:
                    vals["source_match_1_id"] = src_a["match"].id
                    vals["source_type_1"] = src_a.get("result", "winner")

                # Wire source B → away
                if src_b["type"] == "bye":
                    vals["away_team_id"] = src_b["team"].id
                else:
                    vals["source_match_2_id"] = src_b["match"].id
                    vals["source_type_2"] = src_b.get("result", "winner")

                match = Match.create(vals)
                current_matches.append(match)
                all_matches.append(match)

            # Feed next round
            prev_round_sources = [
                {"type": "match", "match": m, "result": "winner"}
                for m in current_matches
            ]

        return all_matches

    @staticmethod
    def _get_round_names(total_rounds):
        """Return round names."""
        names = {}
        names[total_rounds] = "Final"
        if total_rounds >= 2:
            names[total_rounds - 1] = "Semifinal"
        if total_rounds >= 3:
            names[total_rounds - 2] = "Quarterfinal"
        for r in range(1, total_rounds + 1):
            if r not in names:
                names[r] = f"Round {r}"
        return names
