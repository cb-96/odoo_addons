from collections import defaultdict
import json

from odoo import _, api, models
from odoo.exceptions import ValidationError


class FederationStandingsRules(models.AbstractModel):
    _name = "federation.standings.rules"
    _description = "Rules-driven Standings Calculator"

    DEFAULT_TIE_BREAKS = (
        "goal_difference",
        "goals_scored",
        "goals_against",
    )

    @api.model
    def rules_signature(self, rule_set):
        payload = {
            "rule_set_id": rule_set.id if rule_set else False,
            "points": self.points_map(rule_set),
            "tie_breaks": self.tie_breaks(rule_set),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @api.model
    def points_map(self, rule_set):
        values = {
            "win": 3,
            "draw": 1,
            "loss": 0,
            "bye": 0,
            "forfeit_win": 3,
            "forfeit_loss": 0,
        }
        if not rule_set:
            return values
        values.update(
            {
                "win": rule_set.points_win,
                "draw": rule_set.points_draw,
                "loss": rule_set.points_loss,
            }
        )
        values.update(
            {rule.result_type: rule.points for rule in rule_set.points_rule_ids}
        )
        return values

    @api.model
    def tie_breaks(self, rule_set):
        if not rule_set or not rule_set.tie_break_rule_ids:
            return [
                {"type": item, "reverse": item == "goals_against"}
                for item in self.DEFAULT_TIE_BREAKS
            ]
        return [
            {"type": rule.tie_break_type, "reverse": rule.reverse_order}
            for rule in rule_set.tie_break_rule_ids.sorted(
                lambda item: (item.sequence, item.id)
            )
        ]

    @api.model
    def initial_stats(self, carried=None):
        carried = carried or {}
        return {
            "played": carried.get("played", 0),
            "won": carried.get("won", 0),
            "drawn": carried.get("drawn", 0),
            "lost": carried.get("lost", 0),
            "score_for": carried.get("score_for", 0),
            "score_against": carried.get("score_against", 0),
            "points": carried.get("points", 0),
            "fair_play": carried.get("fair_play", 0),
            "ranking_points": carried.get("ranking_points", 0),
            "custom": carried.get("custom", 0),
        }

    @api.model
    def apply_match(self, stats, home_key, away_key, home_score, away_score, points):
        home = stats[home_key]
        away = stats[away_key]
        home["played"] += 1
        away["played"] += 1
        home["score_for"] += home_score
        home["score_against"] += away_score
        away["score_for"] += away_score
        away["score_against"] += home_score
        if home_score > away_score:
            home["won"] += 1
            away["lost"] += 1
            home["points"] += points["win"]
            away["points"] += points["loss"]
        elif away_score > home_score:
            away["won"] += 1
            home["lost"] += 1
            away["points"] += points["win"]
            home["points"] += points["loss"]
        else:
            home["drawn"] += 1
            away["drawn"] += 1
            home["points"] += points["draw"]
            away["points"] += points["draw"]
        return stats

    def _head_to_head(self, tied_keys, matches, points):
        mini = {key: self.initial_stats() for key in tied_keys}
        tied = set(tied_keys)
        for home_key, away_key, home_score, away_score in matches:
            if home_key in tied and away_key in tied:
                self.apply_match(
                    mini, home_key, away_key, home_score, away_score, points
                )
        return mini

    def _criterion_value(self, criterion, key, row, context):
        ctype = criterion["type"]
        if ctype == "head_to_head":
            mini = context["head_to_head"]
            item = mini.get(key) or self.initial_stats()
            return (
                item["points"],
                item["score_for"] - item["score_against"],
                item["score_for"],
            )
        if ctype == "goal_difference":
            return row["score_for"] - row["score_against"]
        if ctype == "goals_scored":
            return row["score_for"]
        if ctype == "goals_against":
            return row["score_against"]
        if ctype in ("fair_play", "ranking_points", "custom"):
            return row.get(ctype, 0)
        if ctype == "drawing_of_lots":
            # Stable pseudo-lot. Recomputes remain reproducible and auditable.
            seed = context.get("lot_seed", 0)
            return (int(key) * 1103515245 + seed * 12345) & 0x7FFFFFFF
        raise ValidationError(
            _("Unsupported tie-break criterion: %(criterion)s", criterion=ctype)
        )

    def _sort_group(self, keys, stats, criteria, matches, points, names, lot_seed):
        if len(keys) < 2 or not criteria:
            return sorted(keys, key=lambda key: (names.get(key, "").casefold(), key))
        criterion = criteria[0]
        context = {"lot_seed": lot_seed}
        if criterion["type"] == "head_to_head":
            context["head_to_head"] = self._head_to_head(keys, matches, points)
        buckets = defaultdict(list)
        for key in keys:
            buckets[self._criterion_value(criterion, key, stats[key], context)].append(
                key
            )
        ordered_values = sorted(buckets, reverse=not criterion["reverse"])
        result = []
        for value in ordered_values:
            bucket = buckets[value]
            result.extend(
                self._sort_group(
                    bucket, stats, criteria[1:], matches, points, names, lot_seed
                )
            )
        return result

    @api.model
    def rank(self, stats, rule_set=False, matches=None, names=None, lot_seed=0):
        matches = matches or []
        names = names or {}
        points = self.points_map(rule_set)
        criteria = self.tie_breaks(rule_set)
        by_points = defaultdict(list)
        for key, row in stats.items():
            by_points[row["points"]].append(key)
        ranked = []
        notes = {}
        rank = 1
        for point_total in sorted(by_points, reverse=True):
            tied = by_points[point_total]
            ordered = self._sort_group(
                tied, stats, criteria, matches, points, names, lot_seed
            )
            for key in ordered:
                notes[key] = self.explain(
                    key, ordered, stats, criteria, matches, points, names, lot_seed
                )
                ranked.append((key, stats[key]))
                stats[key]["rank"] = rank
                rank += 1
        return ranked, notes

    def explain(self, key, ordered, stats, criteria, matches, points, names, lot_seed):
        index = ordered.index(key)
        if index == 0:
            return ""
        previous = ordered[index - 1]
        context = {"lot_seed": lot_seed}
        for criterion in criteria:
            if criterion["type"] == "head_to_head":
                context["head_to_head"] = self._head_to_head(ordered, matches, points)
            left = self._criterion_value(criterion, previous, stats[previous], context)
            right = self._criterion_value(criterion, key, stats[key], context)
            if left != right:
                labels = {
                    "head_to_head": _("head-to-head record"),
                    "goal_difference": _("goal difference"),
                    "goals_scored": _("goals scored"),
                    "goals_against": _("goals against"),
                    "fair_play": _("fair play"),
                    "drawing_of_lots": _("drawing of lots"),
                    "ranking_points": _("ranking points"),
                    "custom": _("custom criterion"),
                }
                return _("Ranked by %(criterion)s", criterion=labels[criterion["type"]])
        return _("Ranked alphabetically by team name")
