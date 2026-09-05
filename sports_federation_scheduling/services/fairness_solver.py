from collections import Counter, defaultdict
from odoo import api, models


class FederationScheduleFairnessSolver(models.AbstractModel):
    _name = "federation.schedule.fairness.solver"
    _description = "Weighted Fairness Schedule Solver"

    @api.model
    def propose(self, schedule, configuration=None, replace_automatic=False):
        schedule.ensure_one()
        cfg = configuration or {
            "same_club_weight": schedule.fairness_same_club_weight,
            "rest_weight": schedule.fairness_rest_weight,
            "consecutive_weight": schedule.fairness_consecutive_weight,
            "time_balance_weight": schedule.fairness_time_balance_weight,
            "court_balance_weight": schedule.fairness_court_balance_weight,
            "preferred_rest_minutes": schedule.preferred_rest_minutes,
            "max_consecutive_games": schedule.max_consecutive_games,
        }
        retained = schedule.assignment_ids.filtered(
            lambda a: not replace_automatic or a.method != "automatic"
        )
        assignment_map = {a.fixture_id.id: a.slot_id.id for a in retained}
        # A physical match day may combine several division structures. The
        # schedule's structure is its creation context, not a boundary for the
        # fixture pool that must be planned and published.
        allocated = schedule.matchday_id.allocation_ids.mapped("fixture_ids")
        fixtures = allocated.filtered(lambda f: f.id not in assignment_map).sorted(
            lambda f: (f.round_number, f.sequence, f.id)
        )
        used_slots = set(assignment_map.values())
        available = schedule.matchday_id.slot_ids.filtered(
            lambda s: s.state == "available" and s.id not in used_slots
        ).sorted(lambda s: (s.start_datetime, s.court_id.id, s.id))
        proposed = []
        for fixture in fixtures:
            best = None
            for slot in available:
                candidate = {**assignment_map, fixture.id: slot.id}
                validation = self.env["federation.schedule.validator"].validate_map(
                    schedule, candidate
                )
                if validation["errors"]:
                    continue
                report = self.evaluate(schedule, candidate, cfg)
                key = self._quality_key(report) + (
                    slot.start_datetime,
                    slot.court_id.id,
                    slot.id,
                )
                if best is None or key < best[0]:
                    best = (key, slot, report)
            if best:
                slot = best[1]
                assignment_map[fixture.id] = slot.id
                proposed.append({"fixture_id": fixture.id, "slot_id": slot.id})
                available -= slot
        assignment_map = self._improve_by_slot_swaps(
            schedule, assignment_map, retained, cfg
        )
        proposed = [
            {"fixture_id": fixture.id, "slot_id": assignment_map[fixture.id]}
            for fixture in fixtures
            if fixture.id in assignment_map
        ]
        final_validation = self.env["federation.schedule.validator"].validate_map(
            schedule, assignment_map
        )
        return {
            "assignments": proposed,
            "unassigned_fixture_ids": final_validation["unassigned_fixture_ids"],
            "validation": final_validation,
            "fairness": self.evaluate(schedule, assignment_map, cfg),
        }

    @api.model
    def _quality_key(self, report):
        """Prefer fewer club clashes before comparing the weighted objective."""
        return (
            report["metrics"]["same_club_simultaneous_pairs"],
            report["weighted_score"],
        )

    @api.model
    def _windows_overlap(self, first_start, first_end, second_start, second_end):
        return first_start < second_end and second_start < first_end

    @api.model
    def _improve_by_slot_swaps(self, schedule, assignment_map, retained, cfg):
        """Deterministically escape greedy local choices with pairwise swaps.

        Retained manual/operational assignments remain pinned. Each accepted swap
        must satisfy all hard validation rules and improve the lexicographic
        objective, where avoiding same-club overlap has first priority.
        """
        result = dict(assignment_map)
        fixed_fixture_ids = set(retained.mapped("fixture_id").ids)
        movable = sorted(set(result) - fixed_fixture_ids)
        validator = self.env["federation.schedule.validator"]
        current_report = self.evaluate(schedule, result, cfg)
        current_key = self._quality_key(current_report)
        max_passes = min(10, max(1, len(movable)))
        for _pass in range(max_passes):
            best = None
            for index, first_id in enumerate(movable):
                for second_id in movable[index + 1 :]:
                    candidate = dict(result)
                    candidate[first_id], candidate[second_id] = (
                        candidate[second_id],
                        candidate[first_id],
                    )
                    if validator.validate_map(schedule, candidate)["errors"]:
                        continue
                    report = self.evaluate(schedule, candidate, cfg)
                    key = self._quality_key(report) + (first_id, second_id)
                    if key[:2] >= current_key:
                        continue
                    if best is None or key < best[0]:
                        best = (key, candidate, report)
            if not best:
                break
            result = best[1]
            current_report = best[2]
            current_key = self._quality_key(current_report)
        return result

    @api.model
    def evaluate(self, schedule, assignment_map, cfg):
        fixture_by_id = {
            f.id: f for f in schedule.matchday_id.allocation_ids.mapped("fixture_ids")
        }
        slot_by_id = {s.id: s for s in schedule.matchday_id.slot_ids}
        team_events = defaultdict(list)
        club_events = defaultdict(list)
        for fixture_id, slot_id in assignment_map.items():
            fixture, slot = fixture_by_id.get(fixture_id), slot_by_id.get(slot_id)
            if not fixture or not slot:
                continue
            for team in (fixture.home_team_id, fixture.away_team_id):
                if not team:
                    continue
                team_events[team.id].append(
                    (slot.start_datetime, slot.end_datetime, slot.court_id.id)
                )
                club = getattr(team, "club_id", False)
                if club:
                    club_events[club.id].append(
                        (
                            slot.start_datetime,
                            slot.end_datetime,
                            fixture.id,
                            team.id,
                        )
                    )
        metrics = {
            "same_club_simultaneous_pairs": 0,
            "rest_shortfall_minutes": 0,
            "excess_consecutive_games": 0,
            "time_balance_spread": 0,
            "same_court_repeats": 0,
        }
        for events in club_events.values():
            for index, first in enumerate(events):
                for second in events[index + 1 :]:
                    if first[2] == second[2] or first[3] == second[3]:
                        continue
                    if self._windows_overlap(first[0], first[1], second[0], second[1]):
                        metrics["same_club_simultaneous_pairs"] += 1
        starts = []
        for events in team_events.values():
            events.sort()
            starts.append([event[0] for event in events])
            court_counts = Counter(event[2] for event in events)
            metrics["same_court_repeats"] += sum(
                max(0, count - 1) for count in court_counts.values()
            )
            streak = 1
            for previous, current in zip(events, events[1:]):
                gap = max(0, int((current[0] - previous[1]).total_seconds() // 60))
                metrics["rest_shortfall_minutes"] += max(
                    0, cfg["preferred_rest_minutes"] - gap
                )
                if gap < cfg["preferred_rest_minutes"]:
                    streak += 1
                    metrics["excess_consecutive_games"] += max(
                        0, streak - cfg["max_consecutive_games"]
                    )
                else:
                    streak = 1
        if starts:
            day_start = min(value for values in starts for value in values)
            centroids = [
                sum((value - day_start).total_seconds() / 60 for value in values)
                / len(values)
                for values in starts
                if values
            ]
            if centroids:
                metrics["time_balance_spread"] = round(
                    max(centroids) - min(centroids), 2
                )
        return self.score_metrics(metrics, cfg)

    @api.model
    def score_metrics(self, metrics, cfg):
        """Score already calculated metrics; kept pure for contract testing."""
        components = {
            "same_club": metrics["same_club_simultaneous_pairs"]
            * cfg["same_club_weight"],
            "rest": metrics["rest_shortfall_minutes"] * cfg["rest_weight"],
            "consecutive": metrics["excess_consecutive_games"]
            * cfg["consecutive_weight"],
            "time_balance": metrics["time_balance_spread"] * cfg["time_balance_weight"],
            "court_balance": metrics["same_court_repeats"]
            * cfg["court_balance_weight"],
        }
        return {
            "weighted_score": round(sum(components.values()), 2),
            "metrics": dict(metrics),
            "components": components,
            "configuration": dict(cfg),
        }
