"""Competition lifecycle rules on top of the stage graph engine.

* knockout results follow the recorded resolution (overtime, forfeit, ...)
  when the score alone cannot decide;
* forfeits and byes earn the points configured on the rule set;
* brackets fed by an earlier stage are generated up front with seed
  placeholders, so they can be scheduled before the source table is final;
* every ranked stage owns one live league table (``federation.standing``),
  computed with this engine and frozen together with the stage;
* withdrawing an approved result undoes what it already decided inside the
  stage, as long as the follow-up match has not been played.
"""

from odoo import _, api, models
from odoo.exceptions import ValidationError

from . import format_presets

RANKED_FORMATS = ("single_round_robin", "double_round_robin")
BRACKET_FORMATS = ("knockout", "placement_bracket")


class FederationStageLifecycle(models.AbstractModel):
    _inherit = "federation.stage.graph.engine"

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------
    def _result(self, fixture):
        """Winner/loser of a fixture, honouring an explicit resolution."""
        match = fixture.operational_match_id
        if (
            not fixture.bye_team_id
            and match
            and match.result_state == "approved"
            and match.include_in_official_standings
        ):
            participants = match.home_team_id | match.away_team_id
            decided = match._get_forfeit_winner()
            if (
                not decided
                and match.home_score == match.away_score
                and match.resolution_type != "regulation"
            ):
                decided = match.advancing_team_id
            if decided and decided in participants:
                return decided, participants - decided
        return super()._result(fixture)

    def _standings(self, stage, team_ids=None):
        rows = super()._standings(stage, team_ids=team_ids)
        rules = self.env["federation.standings.rules"]
        points = rules.points_map(stage._get_effective_rule_set())
        forfeits = stage.stage_fixture_ids.filtered(
            lambda fixture: fixture.operational_match_id
            and fixture.operational_match_id.result_state == "approved"
            and fixture.operational_match_id.include_in_official_standings
            and rules.match_forfeit_side(fixture.operational_match_id)
        )
        byes = stage.stage_fixture_ids.filtered("bye_team_id")
        if not forfeits and not (byes and points.get("bye")):
            return rows
        return self._rank_with_adjustments(stage, team_ids, points, forfeits, byes)

    def _rank_with_adjustments(self, stage, team_ids, points, forfeits, byes):
        """Recompute a table where forfeits or byes change the points."""
        rules = self.env["federation.standings.rules"]
        participants = stage.stage_participant_ids
        if team_ids is not None:
            participants = participants.filtered(
                lambda participant: participant.team_id.id in set(team_ids)
            )
        stats = {
            participant.team_id.id: rules.initial_stats(
                {
                    "played": participant.carried_played,
                    "score_for": participant.carried_score_for,
                    "score_against": participant.carried_score_against,
                    "points": participant.carried_points,
                }
            )
            for participant in participants
        }
        matches = []
        for fixture in stage.stage_fixture_ids.filtered(
            lambda item: item.operational_match_id
            and item.operational_match_id.result_state == "approved"
            and item.operational_match_id.include_in_official_standings
            and item.home_team_id
            and item.away_team_id
        ):
            match = fixture.operational_match_id
            home_key, away_key = match.home_team_id.id, match.away_team_id.id
            if home_key not in stats or away_key not in stats:
                continue
            rules.apply_match(
                stats,
                home_key,
                away_key,
                match.home_score,
                match.away_score,
                points,
                forfeit_winner=(
                    rules.match_forfeit_side(match) if fixture in forfeits else None
                ),
            )
            matches.append((home_key, away_key, match.home_score, match.away_score))
        for fixture in byes:
            rules.apply_bye(stats, fixture.bye_team_id.id, points)
        names = {
            participant.team_id.id: participant.team_id.name or ""
            for participant in stage.stage_participant_ids
        }
        ranked, notes = rules.rank(
            stats,
            rule_set=stage._get_effective_rule_set(),
            matches=matches,
            names=names,
            lot_seed=stage.id,
        )
        team_by_id = {
            participant.team_id.id: participant.team_id
            for participant in stage.stage_participant_ids
        }
        return [
            dict(row, team=team_by_id[key], tiebreak_notes=notes[key])
            for key, row in ranked
        ]

    # ------------------------------------------------------------------
    # Placeholder brackets
    # ------------------------------------------------------------------
    @api.model
    def _expected_progression_count(self, stage):
        return sum(
            edge.rank_to - edge.rank_from + 1
            for edge in stage.incoming_progression_ids.filtered("active")
        )

    @api.model
    def _has_seed_placeholders(self, stage):
        return bool(
            stage.stage_fixture_ids.filtered(
                lambda fixture: fixture.home_source_seed or fixture.away_source_seed
            )
        )

    @api.model
    def prepare_placeholder_stage(self, stage):
        """Build a progression stage before its teams are known.

        Brackets and round robins both get every fixture now, referencing
        stage seeds ("#1 Group A") that progression fills in later.
        """
        if (
            stage.source_type != "progression"
            or stage.format_type not in BRACKET_FORMATS + RANKED_FORMATS
            or stage.stage_fixture_ids
            or stage.stage_participant_ids
        ):
            return False
        count = self._expected_progression_count(stage)
        if count < 2:
            return False
        if stage.format_type in RANKED_FORMATS:
            self._round_robin_placeholders(
                stage, count, stage.format_type == "double_round_robin"
            )
        else:
            self._knockout(
                stage,
                stage.format_type == "placement_bracket",
                placeholder_count=count,
            )
        stage.graph_state = "waiting"
        return True

    @api.model
    def _round_robin_placeholders(self, stage, count, double):
        """Round robin between stage seeds 1..count, teams filled later."""
        return self.env["federation.fixture"].create(
            [
                {
                    "structure_id": stage.structure_id.id,
                    "stage_id": stage.id,
                    "round_number": round_number,
                    "sequence": sequence * 10,
                    "home_source_seed": home,
                    "away_source_seed": away,
                }
                for round_number, pairs in enumerate(
                    format_presets.round_robin_pairs(count, double), 1
                )
                for sequence, (home, away) in enumerate(pairs, 1)
            ]
        )

    @api.model
    def _fill_seeded_stage(self, stage):
        """Put the progressed teams into the pre-built placeholder bracket."""
        team_by_seed = {
            participant.seed: participant.team_id
            for participant in stage.stage_participant_ids
        }
        for fixture in stage.stage_fixture_ids.sorted(
            lambda item: (item.round_number, item.sequence, item.id)
        ):
            values = {}
            for side in ("home", "away"):
                seed = fixture["%s_source_seed" % side]
                team = team_by_seed.get(seed) if seed else False
                if team and not fixture["%s_team_id" % side]:
                    values["%s_team_id" % side] = team.id
            if values:
                fixture.write(values)
        stage.graph_state = "ready"
        self._resolve_stage_byes(stage)
        playable = stage.stage_fixture_ids.filtered(
            lambda fixture: fixture.state == "ready"
            and fixture.home_team_id
            and fixture.away_team_id
            and not fixture.operational_match_id
        )
        if playable:
            self.env["federation.fixture.materializer"].materialize(playable)
        return True

    def _resolve_bye(self, fixture):
        # A seed placeholder is not a missing opponent: wait for progression.
        for side in ("home", "away"):
            if fixture["%s_source_seed" % side] and not fixture["%s_team_id" % side]:
                return
        return super()._resolve_bye(fixture)

    def prepare_stage(self, stage):
        if stage.source_type == "progression" and self._has_seed_placeholders(stage):
            if len(stage.stage_participant_ids) >= self._expected_progression_count(
                stage
            ):
                result = self._fill_seeded_stage(stage)
                self._ensure_linked_standing(stage)
                return result
            stage.graph_state = "waiting"
            return True
        result = super().prepare_stage(stage)
        self._ensure_linked_standing(stage)
        return result

    # ------------------------------------------------------------------
    # One live table per ranked stage
    # ------------------------------------------------------------------
    @api.model
    def _ensure_linked_standing(self, stage):
        """Create or refresh the league table that shows this stage.

        The table and its participants are derived from the stage, which the
        caller was already allowed to prepare; they are written elevated so a
        competition designer does not need standings-manager rights.
        """
        stage = stage.sudo()
        if stage.format_type not in RANKED_FORMATS or not stage.stage_participant_ids:
            return False
        division = stage.structure_id.division_id
        if not division:
            return False
        Participant = self.env["federation.tournament.participant"].sudo()
        existing = {
            participant.team_id.id
            for participant in Participant.search([("tournament_id", "=", division.id)])
        }
        missing = stage.stage_participant_ids.mapped("team_id").filtered(
            lambda team: team.id not in existing
        )
        if missing:
            # Teams reached this stage through registration or progression,
            # which apply the same division eligibility check.
            Participant.create(
                [
                    {
                        "tournament_id": division.id,
                        "team_id": team.id,
                        "state": "confirmed",
                    }
                    for team in missing
                ]
            )
        Standing = self.env["federation.standing"].sudo()
        standing = Standing.with_context(active_test=False).search(
            [("structure_stage_id", "=", stage.id)], limit=1
        )
        if not standing:
            standing = Standing.create(
                {
                    "name": stage.name or division.name,
                    "tournament_id": division.id,
                    "structure_stage_id": stage.id,
                }
            )
        elif not standing.active:
            standing.active = True
        superseded = Standing.search(
            [
                ("tournament_id", "=", division.id),
                ("structure_stage_id", "!=", False),
                ("structure_stage_id.structure_id", "!=", stage.structure_id.id),
            ]
        )
        if superseded:
            superseded.write({"active": False})
        if standing.state != "frozen":
            standing.action_recompute()
        return standing

    @api.model
    def freeze_standings(self, stage):
        result = super().freeze_standings(stage)
        standings = (
            self.env["federation.standing"]
            .sudo()
            .search([("structure_stage_id", "=", stage.id), ("state", "!=", "frozen")])
        )
        if standings:
            standings.with_context(stage_engine_freeze=True).action_freeze()
        return result

    # ------------------------------------------------------------------
    # Corrections
    # ------------------------------------------------------------------
    @api.model
    def reopen_dependants(self, fixture):
        """Undo the effect of a withdrawn result on later fixtures."""
        targets = self.env["federation.fixture"].search(
            [
                "|",
                ("home_source_fixture_id", "=", fixture.id),
                ("away_source_fixture_id", "=", fixture.id),
            ]
        )
        for target in targets:
            values = {}
            for side in ("home", "away"):
                if (
                    target["%s_source_fixture_id" % side] == fixture
                    and target["%s_team_id" % side]
                ):
                    values["%s_team_id" % side] = False
            if not values and not target.bye_team_id:
                continue
            match = target.operational_match_id
            if match:
                self._assert_match_unplayed(match)
            if target.bye_team_id:
                values.update({"bye_team_id": False, "state": "ready"})
            if match:
                target.operational_match_id = False
                # The follow-up match was never played and its teams were wrong.
                # Its gameday rosters and official assignments go with it; the
                # match is recreated in the same scheduled slot once the
                # corrected result is approved.
                self.env["federation.competition.event"].sudo().emit(
                    fixture.edition_id,
                    "follow_up_match_withdrawn",
                    {
                        "fixture_id": target.id,
                        "match_id": match.id,
                        "source_fixture_id": fixture.id,
                    },
                )
                match.sudo().unlink()
            target.write(values)
            self.reopen_dependants(target)
        return True

    @api.model
    def _assert_match_unplayed(self, match):
        played = match.state in ("in_progress", "done") or match.result_state != "draft"
        for model_name in ("federation.court.capture", "federation.matchday.deviation"):
            model = self.env.get(model_name)
            if model is not None and model.sudo().search_count(
                [("match_id", "=", match.id)], limit=1
            ):
                played = True
        if played:
            raise ValidationError(
                _(
                    "%(match)s already used this result and has started or has a "
                    "result. Correct that match first, then this one."
                )
                % {"match": match.display_name}
            )
