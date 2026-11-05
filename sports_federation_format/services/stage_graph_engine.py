from math import ceil, log2

from odoo import _, api, models
from odoo.exceptions import ValidationError

from . import format_presets


class FederationStageGraphEngine(models.AbstractModel):
    _name = "federation.stage.graph.engine"
    _description = "Stage Graph Engine"

    @api.model
    def generate_pool_knockout_stages(self, structure):
        """Create round-robin groups and a cross-seeded knockout.

        ``qualifiers_per_pool`` teams of every group advance. Group winners
        take the best seeds, then runners-up, rotated so teams from one group
        avoid each other in the first knockout round where possible.
        """
        pool_count = structure.pool_count
        if pool_count < 1:
            raise ValidationError(_("A pool-knockout format needs at least one pool."))
        lines = structure.participant_set_id.line_ids.sorted(
            lambda line: (line.seed or 9999, line.id)
        )
        estimate = format_presets.plan(
            "pool_knockout", len(lines), **structure._preset_options()
        )
        if not estimate["feasible"]:
            raise ValidationError(estimate["message"])
        positions = format_presets.snake_pools(len(lines), pool_count)
        group_format = (
            "double_round_robin"
            if structure.first_phase_double
            else "single_round_robin"
        )
        stages = self.env["federation.structure.stage"]
        pool_stages = []
        for index, pool_positions in enumerate(positions):
            stage = stages.create(
                {
                    "name": _(
                        "%(structure)s - Group %(letter)s",
                        structure=structure.name,
                        letter=format_presets.group_letter(index),
                    ),
                    "structure_id": structure.id,
                    "sequence": (index + 1) * 10,
                    "stage_type": "pool",
                    "format_type": group_format,
                    "source_type": "manual",
                }
            )
            self.env["federation.stage.participant"].create(
                [
                    {
                        "stage_id": stage.id,
                        "team_id": lines[position].team_id.id,
                        "seed": seed,
                        "source_rank": lines[position].seed or seed,
                    }
                    for seed, position in enumerate(pool_positions, 1)
                ]
            )
            pool_stages.append(stage)

        final_stage = stages.create(
            {
                "name": _("%s - Knockout") % structure.name,
                "structure_id": structure.id,
                "sequence": (pool_count + 1) * 10,
                "stage_type": "placement" if structure.knockout_full_placement else "knockout",
                "format_type": (
                    "placement_bracket"
                    if structure.knockout_full_placement
                    else "knockout"
                ),
                "source_type": "progression",
            }
        )
        sizes = [len(pool_positions) for pool_positions in positions]
        Progression = self.env["federation.structure.stage.progression"]
        Progression.create(
            [
                {
                    "name": _(
                        "#%(rank)s %(group)s to knockout seed %(seed)s",
                        rank=rank,
                        group=pool_stages[pool_index].name,
                        seed=seed,
                    ),
                    "source_stage_id": pool_stages[pool_index].id,
                    "target_stage_id": final_stage.id,
                    "rank_from": rank,
                    "rank_to": rank,
                    "target_seed_from": seed,
                }
                for pool_index, rank, seed in format_presets.cross_seed(
                    sizes, structure.qualifiers_per_pool
                )
            ]
        )
        return pool_stages + [final_stage]

    @api.model
    def generate_split_stages(self, structure):
        """Regular season, then a top group and (optionally) a bottom group.

        With every team in the top group this is a season played in two
        halves with a fresh or carried-over table.
        """
        teams = len(structure.participant_set_id.line_ids)
        top = structure._effective_split_rank()
        estimate = format_presets.plan(
            "split_pools", teams, **structure._preset_options()
        )
        if not estimate["feasible"]:
            raise ValidationError(estimate["message"])
        Stage = self.env["federation.structure.stage"]
        second_format = (
            "double_round_robin" if structure.second_phase_double else "single_round_robin"
        )
        season = Stage.create(
            {
                "name": _("%s - Regular season") % structure.name,
                "structure_id": structure.id,
                "sequence": 10,
                "stage_type": "league",
                "format_type": (
                    "double_round_robin"
                    if structure.first_phase_double
                    else "single_round_robin"
                ),
                "source_type": "registration",
            }
        )
        bottom = teams - top
        groups = [
            (
                _("%s - Championship group") % structure.name
                if bottom
                else _("%s - Second half") % structure.name,
                1,
                top,
                1,
            )
        ]
        if bottom:
            groups.append(
                (_("%s - Relegation group") % structure.name, top + 1, teams, top + 1)
            )
        created = [season]
        for sequence, (name, rank_from, rank_to, final_rank_from) in enumerate(groups, 2):
            stage = Stage.create(
                {
                    "name": name,
                    "structure_id": structure.id,
                    "sequence": sequence * 10,
                    "stage_type": "league",
                    "format_type": second_format,
                    "source_type": "progression",
                    "carryover_policy": structure.second_phase_carryover,
                    "final_rank_from": final_rank_from,
                    "final_rank_to": final_rank_from + rank_to - rank_from,
                }
            )
            self.env["federation.structure.stage.progression"].create(
                {
                    "name": _(
                        "Places %(start)s-%(end)s to %(stage)s",
                        start=rank_from,
                        end=rank_to,
                        stage=name,
                    ),
                    "source_stage_id": season.id,
                    "target_stage_id": stage.id,
                    "rank_from": rank_from,
                    "rank_to": rank_to,
                    "target_seed_from": 1,
                }
            )
            created.append(stage)
        return created

    @api.model
    def validate_graph(self, structure):
        return self.env["federation.stage.graph.validator"].validate(structure)

    def _participants(self, stage):
        return stage.stage_participant_ids.sorted(lambda p: (p.seed, p.id))

    @api.model
    def prepare_stage(self, stage):
        self.validate_graph(stage.structure_id)
        if stage.source_type == "registration":
            stage.stage_participant_ids.unlink()
            self.env["federation.stage.participant"].create(
                [
                    {
                        "stage_id": stage.id,
                        "team_id": x.team_id.id,
                        "seed": x.seed or i,
                        "source_rank": x.seed or i,
                    }
                    for i, x in enumerate(
                        stage.structure_id.participant_set_id.line_ids.sorted(
                            lambda x: (x.seed or 9999, x.id)
                        ),
                        1,
                    )
                ]
            )
        elif stage.source_type == "progression" and not stage.stage_participant_ids:
            stage.graph_state = "waiting"
            return True
        if len(stage.stage_participant_ids) < 2:
            raise ValidationError(_("A stage requires at least two teams."))
        stage.stage_fixture_ids.unlink()
        if stage.format_type in ("single_round_robin", "double_round_robin"):
            self._round_robin(stage, stage.format_type == "double_round_robin")
        elif stage.format_type == "knockout":
            self._knockout(stage, False)
        elif stage.format_type == "placement_bracket":
            self._knockout(stage, True)
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

    def _round_robin(self, stage, double):
        return self.env["federation.fixture.generator.round.robin"].generate(
            stage, self._participants(stage), double=double
        )

    def _seed_order(self, size):
        order = [1, 2]
        while len(order) < size:
            mirror = len(order) * 2 + 1
            order = [x for seed in order for x in (seed, mirror - seed)]
        return order

    def _knockout(self, stage, full_placement, placeholder_count=0):
        """Generate a bracket.

        With ``placeholder_count`` the bracket is built before its teams are
        known: first-round fixtures reference stage seeds that progression
        fills in later, so the whole bracket can be scheduled in advance.
        """
        if placeholder_count:
            count = placeholder_count
            by_seed = {seed: None for seed in range(1, count + 1)}
        else:
            participants = self._participants(stage)
            count = len(participants)
            by_seed = {p.seed: p.team_id for p in participants}
        if set(by_seed) != set(range(1, count + 1)):
            raise ValidationError(
                _("Bracket seeds must be consecutive from 1 to %(count)s.", count=count)
            )
        size = 2 ** ceil(log2(count))
        order = self._seed_order(size)
        F = self.env["federation.fixture"]
        common = {"structure_id": stage.structure_id.id, "stage_id": stage.id}
        current = []
        cohorts = []
        for i in range(0, size, 2):
            a, b = by_seed.get(order[i]), by_seed.get(order[i + 1])
            current.append(
                F.create(
                    {
                        **common,
                        "round_number": 1,
                        "sequence": i * 5 + 10,
                        "home_team_id": a.id if a else False,
                        "away_team_id": b.id if b else False,
                        "home_source_seed": (
                            order[i] if placeholder_count and order[i] <= count else 0
                        ),
                        "away_source_seed": (
                            order[i + 1]
                            if placeholder_count and order[i + 1] <= count
                            else 0
                        ),
                        "placement_from": 1,
                        "placement_to": count,
                    }
                )
            )
        rnd = 1
        while len(current) > 1:
            cohorts.append(current)
            rnd += 1
            nxt = []
            for i in range(0, len(current), 2):
                nxt.append(
                    F.create(
                        {
                            **common,
                            "round_number": rnd,
                            "sequence": i * 5 + 10,
                            "home_source_fixture_id": current[i].id,
                            "home_source_outcome": "winner",
                            "away_source_fixture_id": current[i + 1].id,
                            "away_source_outcome": "winner",
                        }
                    )
                )
            current = nxt
        current[0].write({"placement_from": 1, "placement_to": 2})
        if full_placement:
            rank = 3
            for cohort in reversed(cohorts):
                sources = [(f, "loser") for f in cohort if self._can_produce_loser(f)]
                if len(sources) > 1:
                    rnd = self._classification(
                        stage,
                        sources,
                        rank,
                        min(count, rank + len(sources) - 1),
                        rnd + 1,
                    )
                    rank += len(sources)
        for f in stage.stage_fixture_ids.sorted(
            lambda x: (x.round_number, x.sequence, x.id)
        ):
            self._resolve_bye(f)

    def _can_produce_loser(self, f):
        return (
            sum(
                bool(x)
                for x in (
                    f.home_team_id,
                    f.away_team_id,
                    f.home_source_fixture_id,
                    f.away_source_fixture_id,
                )
            )
            >= 2
        )

    def _classification(self, stage, sources, lo, hi, rnd):
        F = self.env["federation.fixture"]
        common = {"structure_id": stage.structure_id.id, "stage_id": stage.id}
        if len(sources) == 2:
            a, ao = sources[0]
            b, bo = sources[1]
            F.create(
                {
                    **common,
                    "round_number": rnd,
                    "sequence": 1000 + lo * 10,
                    "home_source_fixture_id": a.id,
                    "home_source_outcome": ao,
                    "away_source_fixture_id": b.id,
                    "away_source_outcome": bo,
                    "placement_from": lo,
                    "placement_to": hi,
                }
            )
            return rnd
        winners = []
        losers = []
        for i in range(0, len(sources) - 1, 2):
            a, ao = sources[i]
            b, bo = sources[i + 1]
            f = F.create(
                {
                    **common,
                    "round_number": rnd,
                    "sequence": 1000 + lo * 10 + i,
                    "home_source_fixture_id": a.id,
                    "home_source_outcome": ao,
                    "away_source_fixture_id": b.id,
                    "away_source_outcome": bo,
                    "placement_from": lo,
                    "placement_to": hi,
                }
            )
            winners.append((f, "winner"))
            losers.append((f, "loser"))
        if len(sources) % 2:
            winners.append(sources[-1])
        split = lo + len(winners) - 1
        last = rnd
        if len(winners) > 1:
            last = max(last, self._classification(stage, winners, lo, split, rnd + 1))
        if len(losers) > 1:
            last = max(
                last, self._classification(stage, losers, split + 1, hi, rnd + 1)
            )
        return last

    def _result(self, fixture):
        if fixture.bye_team_id:
            return fixture.bye_team_id, self.env["federation.team"]
        match = fixture.operational_match_id
        if (
            not match
            or match.result_state != "approved"
            or not match.include_in_official_standings
        ):
            return False, False
        if match.home_score == match.away_score:
            raise ValidationError(
                _(
                    "A tied result cannot determine progression without an explicit tie-break outcome."
                )
            )
        return (
            (match.home_team_id, match.away_team_id)
            if match.home_score > match.away_score
            else (match.away_team_id, match.home_team_id)
        )

    def _resolve_bye(self, fixture):
        if fixture.operational_match_id or fixture.bye_team_id:
            return
        unresolved_home = fixture.home_source_fixture_id and not fixture.home_team_id
        unresolved_away = fixture.away_source_fixture_id and not fixture.away_team_id
        if unresolved_home or unresolved_away:
            return
        team = fixture.home_team_id or fixture.away_team_id
        if team and bool(fixture.home_team_id) != bool(fixture.away_team_id):
            fixture.write({"bye_team_id": team.id, "state": "completed"})
            self.resolve_dependants(fixture)

    def _resolve_stage_byes(self, stage):
        for fixture in stage.stage_fixture_ids.sorted(
            lambda item: (item.round_number, item.sequence, item.id)
        ):
            self._resolve_bye(fixture)
        return True

    @api.model
    def resolve_dependants(self, f):
        winner, loser = self._result(f)
        if not winner:
            return True
        for target in self.env["federation.fixture"].search(
            [
                "|",
                ("home_source_fixture_id", "=", f.id),
                ("away_source_fixture_id", "=", f.id),
            ]
        ):
            vals = {}
            if target.home_source_fixture_id == f:
                vals["home_team_id"] = (
                    winner if target.home_source_outcome == "winner" else loser
                ).id
            if target.away_source_fixture_id == f:
                vals["away_team_id"] = (
                    winner if target.away_source_outcome == "winner" else loser
                ).id
            target.write(vals)
            self._resolve_bye(target)
            if (
                target.state == "ready"
                and target.home_team_id
                and target.away_team_id
                and not target.operational_match_id
            ):
                self.env["federation.fixture.materializer"].materialize(target)
        return True

    def _standings(self, stage, team_ids=None):
        engine = self.env["federation.standings.rules"]
        rule_set = stage._get_effective_rule_set()
        points = engine.points_map(rule_set)
        participants = stage.stage_participant_ids
        if team_ids is not None:
            participants = participants.filtered(
                lambda participant: participant.team_id.id in set(team_ids)
            )
        stats = {
            participant.team_id.id: engine.initial_stats(
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
            home_key = match.home_team_id.id
            away_key = match.away_team_id.id
            if home_key not in stats or away_key not in stats:
                continue
            engine.apply_match(
                stats, home_key, away_key, match.home_score, match.away_score, points
            )
            matches.append((home_key, away_key, match.home_score, match.away_score))
        names = {
            participant.team_id.id: participant.team_id.name or ""
            for participant in stage.stage_participant_ids
        }
        ranked, notes = engine.rank(
            stats,
            rule_set=rule_set,
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

    @api.model
    def freeze_standings(self, stage):
        incomplete = stage.stage_fixture_ids.filtered(
            lambda fixture: not fixture.bye_team_id
            and (
                not fixture.operational_match_id
                or fixture.operational_match_id.result_state != "approved"
                or not fixture.operational_match_id.include_in_official_standings
            )
        )
        if incomplete:
            raise ValidationError(_("Approve all operational match results first."))
        rule_set = stage._get_effective_rule_set()
        rules_engine = self.env["federation.standings.rules"]
        snap = self.env["federation.stage.standing.snapshot"].create(
            {
                "stage_id": stage.id,
                "rule_set_id": rule_set.id if rule_set else False,
                "rules_signature": rules_engine.rules_signature(rule_set),
            }
        )
        if rule_set and not rule_set.locked:
            rule_set.action_lock()
        self.env["federation.stage.standing.line"].create(
            [
                {
                    "snapshot_id": snap.id,
                    "team_id": x["team"].id,
                    **{
                        k: x[k]
                        for k in (
                            "rank",
                            "played",
                            "won",
                            "drawn",
                            "lost",
                            "score_for",
                            "score_against",
                            "points",
                            "tiebreak_notes",
                        )
                    },
                }
                for x in self._standings(stage)
            ]
        )
        stage.write({"standing_snapshot_id": snap.id, "graph_state": "frozen"})
        for edge in stage.outgoing_progression_ids.filtered(
            lambda e: e.active and not e.applied
        ):
            self.apply_progression(edge)

    def apply_progression(self, e):
        lines = e.source_stage_id.standing_snapshot_id.line_ids.filtered(
            lambda line: e.rank_from <= line.rank <= e.rank_to
        ).sorted("rank")
        target = e.target_stage_id
        same_group = {}
        if target.carryover_policy == "same_group_results":
            same_group = {
                row["team"].id: row
                for row in self._standings(
                    e.source_stage_id,
                    team_ids=lines.mapped("team_id").ids,
                )
            }
        self.env["federation.stage.participant"].create(
            [
                {
                    "stage_id": target.id,
                    "team_id": x.team_id.id,
                    "seed": e.target_seed_from + i,
                    "source_rank": x.rank,
                    "carried_points": (
                        x.points
                        if target.carryover_policy == "full_points"
                        else same_group.get(x.team_id.id, {}).get("points", 0)
                    ),
                    "carried_played": (
                        x.played
                        if target.carryover_policy == "full_points"
                        else same_group.get(x.team_id.id, {}).get("played", 0)
                    ),
                    "carried_score_for": (
                        x.score_for
                        if target.carryover_policy == "full_points"
                        else same_group.get(x.team_id.id, {}).get("score_for", 0)
                    ),
                    "carried_score_against": (
                        x.score_against
                        if target.carryover_policy == "full_points"
                        else same_group.get(x.team_id.id, {}).get("score_against", 0)
                    ),
                }
                for i, x in enumerate(lines)
            ]
        )
        e.applied = True
        expected = sum(
            x.rank_to - x.rank_from + 1
            for x in target.incoming_progression_ids.filtered(lambda x: x.active)
        )
        if len(target.stage_participant_ids) >= expected:
            self.prepare_stage(target)
