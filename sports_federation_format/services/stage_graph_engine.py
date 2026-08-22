from collections import defaultdict
from math import ceil, log2
from odoo import _, api, models
from odoo.exceptions import ValidationError


class FederationStageGraphEngine(models.AbstractModel):
    _name = "federation.stage.graph.engine"
    _description = "Stage Graph Engine"

    @api.model
    def validate_graph(self, structure):
        adj = {s.id: [] for s in structure.stage_ids}
        visiting = set()
        done = set()
        for e in self.env["federation.structure.stage.progression"].search(
            [("structure_id", "=", structure.id), ("active", "=", True)]
        ):
            adj[e.source_stage_id.id].append(e.target_stage_id.id)

        def visit(n):
            if n in visiting:
                raise ValidationError(_("Stage graph contains a cycle."))
            if n in done:
                return
            visiting.add(n)
            for x in adj[n]:
                visit(x)
            visiting.remove(n)
            done.add(n)

        for stage in structure.stage_ids:
            visit(stage.id)
        return True

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
        return True

    def _round_robin(self, stage, double):
        teams = list(self._participants(stage).mapped("team_id"))
        work = teams + [False] if len(teams) % 2 else teams[:]
        rounds = []
        for rnd in range(len(work) - 1):
            pairs = []
            for i in range(len(work) // 2):
                a, b = work[i], work[-i - 1]
                if a and b:
                    pairs.append((a, b) if rnd % 2 == 0 else (b, a))
            rounds.append(pairs)
            work = [work[0], work[-1], *work[1:-1]]
        if double:
            rounds += [[(b, a) for a, b in pairs] for pairs in rounds]
        self.env["federation.fixture"].create(
            [
                {
                    "structure_id": stage.structure_id.id,
                    "stage_id": stage.id,
                    "round_number": rn,
                    "sequence": seq * 10,
                    "home_team_id": a.id,
                    "away_team_id": b.id,
                }
                for rn, pairs in enumerate(rounds, 1)
                for seq, (a, b) in enumerate(pairs, 1)
            ]
        )

    def _seed_order(self, size):
        order = [1, 2]
        while len(order) < size:
            mirror = len(order) * 2 + 1
            order = [x for seed in order for x in (seed, mirror - seed)]
        return order

    def _knockout(self, stage, full_placement):
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

    def _result(self, f):
        if f.result_state != "approved":
            return False, False
        return (
            (f.home_team_id, f.away_team_id)
            if f.home_score > f.away_score
            else (f.away_team_id, f.home_team_id)
        )

    def _resolve_bye(self, f):
        if f.result_state == "approved":
            return
        if f.home_team_id and not f.away_team_id and not f.away_source_fixture_id:
            f.write(
                {
                    "home_score": 1,
                    "away_score": 0,
                    "result_state": "approved",
                    "state": "completed",
                }
            )
            self.resolve_dependants(f)
        elif f.away_team_id and not f.home_team_id and not f.home_source_fixture_id:
            f.write(
                {
                    "home_score": 0,
                    "away_score": 1,
                    "result_state": "approved",
                    "state": "completed",
                }
            )
            self.resolve_dependants(f)

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
        return True

    def _standings(self, stage):
        stats = {
            p.team_id.id: {
                "team": p.team_id,
                "played": p.carried_played,
                "won": 0,
                "drawn": 0,
                "lost": 0,
                "score_for": p.carried_score_for,
                "score_against": p.carried_score_against,
                "points": p.carried_points,
            }
            for p in stage.stage_participant_ids
        }
        for f in stage.stage_fixture_ids.filtered(
            lambda x: x.result_state == "approved" and x.home_team_id and x.away_team_id
        ):
            h, a = stats[f.home_team_id.id], stats[f.away_team_id.id]
            h["played"] += 1
            a["played"] += 1
            h["score_for"] += f.home_score
            h["score_against"] += f.away_score
            a["score_for"] += f.away_score
            a["score_against"] += f.home_score
            if f.home_score > f.away_score:
                h["won"] += 1
                a["lost"] += 1
                h["points"] += 3
            elif f.away_score > f.home_score:
                a["won"] += 1
                h["lost"] += 1
                a["points"] += 3
            else:
                h["drawn"] += 1
                a["drawn"] += 1
                h["points"] += 1
                a["points"] += 1
        rows = sorted(
            stats.values(),
            key=lambda x: (
                -x["points"],
                -(x["score_for"] - x["score_against"]),
                -x["score_for"],
                x["team"].name,
            ),
        )
        for i, x in enumerate(rows, 1):
            x["rank"] = i
        return rows

    @api.model
    def freeze_standings(self, stage):
        if stage.stage_fixture_ids.filtered(lambda f: f.result_state != "approved"):
            raise ValidationError(_("Approve all results first."))
        snap = self.env["federation.stage.standing.snapshot"].create(
            {"stage_id": stage.id}
        )
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
            lambda l: e.rank_from <= l.rank <= e.rank_to
        ).sorted("rank")
        target = e.target_stage_id
        self.env["federation.stage.participant"].create(
            [
                {
                    "stage_id": target.id,
                    "team_id": x.team_id.id,
                    "seed": e.target_seed_from + i,
                    "source_rank": x.rank,
                    "carried_points": (
                        x.points if target.carryover_policy == "full_points" else 0
                    ),
                    "carried_played": (
                        x.played if target.carryover_policy == "full_points" else 0
                    ),
                    "carried_score_for": (
                        x.score_for if target.carryover_policy == "full_points" else 0
                    ),
                    "carried_score_against": (
                        x.score_against
                        if target.carryover_policy == "full_points"
                        else 0
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
