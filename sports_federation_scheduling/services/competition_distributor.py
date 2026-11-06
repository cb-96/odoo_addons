from collections import Counter, defaultdict
from math import ceil

from odoo import models


class FederationCompetitionScheduleDistributor(models.AbstractModel):
    _name = "federation.competition.schedule.distributor"
    _description = "Competition Fixture to Match-Day Distributor"

    def propose(self, fixtures, capacities, pinned=None, known_days=None):
        """Distribute fixtures deterministically using real per-day capacity.

        Besides capacity and the divisions playing on a day, every fixture
        respects its stage:

        * a stage limited to some game days is only planned on those days;
        * a stage fed by earlier stages (knockout after groups, second half
          after the regular season) is planned no earlier than the last day
          of those stages. When a source stage spans several game days the
          next stage starts on a later day; a source stage played on a single
          day (tournament day) may be followed on that same day;
        * a follow-up match ("Winner R1 M2") is never planned on an earlier
          day than the match deciding its team.

        ``known_days`` maps fixtures already allocated outside this run to
        their game-day date, so chronology also holds across runs.

        Each team's matches are spread over the game days its division plays:

        * a day may carry ``team_limit`` (the most matches one team can play
          there with the required rest); a team is not given more matches on
          that day while another fitting day has room;
        * every team gets a fair share per day (its matches divided by the
          division's game days), and days where it is still under that share
          are preferred.
        """
        pinned = pinned or {}
        known_days = dict(known_days or {})
        days = sorted(capacities, key=lambda item: (item["date"], item["matchday_id"]))
        date_by_day = {item["matchday_id"]: item["date"] for item in days}
        remaining = {item["matchday_id"]: item["capacity"] for item in days}
        assignments = defaultdict(list)
        team_days = defaultdict(set)
        errors = []
        fixtures_by_id = {fixture.id: fixture for fixture in fixtures}
        placed_dates = dict(known_days)
        stage_dates = defaultdict(set)
        for fixture_id, date in known_days.items():
            fixture = fixtures.browse(fixture_id).exists()
            if fixture:
                stage_dates[fixture.stage_id.id].add(date)

        # Game days may be limited to some divisions ("division_ids"); an
        # empty or missing set means every division may play on that day.
        allowed_divisions = {
            day["matchday_id"]: set(day.get("division_ids") or ()) for day in days
        }

        def allows(day_id, fixture):
            allowed = allowed_divisions.get(day_id)
            return not allowed or fixture.division_id.id in allowed

        def stage_allows(day_id, fixture):
            windows = self._stage_day_ids(fixture)
            return not windows or day_id in windows

        def earliest(fixture):
            """(date, strictly_after) the fixture must respect, or None."""
            bound = None
            for source_stage in self._source_stages(fixture):
                dates = stage_dates.get(source_stage.id)
                if not dates:
                    continue
                candidate = (max(dates), len(dates) > 1)
                if bound is None or candidate > bound:
                    bound = candidate
            for source in (
                fixture.home_source_fixture_id,
                fixture.away_source_fixture_id,
            ):
                date = placed_dates.get(source.id) if source else None
                if date and (bound is None or (date, False) > bound):
                    bound = (date, False)
            return bound

        def chronology_allows(day_id, bound):
            if not bound:
                return True
            date, strictly_after = bound
            day_date = date_by_day[day_id]
            return day_date > date if strictly_after else day_date >= date

        round_days = defaultdict(set)

        def assign(fixture, day_id):
            self._assign(fixture, day_id, assignments, team_days, remaining)
            team_load[day_id].update(self._team_ids(fixture))
            round_days[day_id].add((fixture.stage_id.id, fixture.round_number))
            placed_dates[fixture.id] = date_by_day[day_id]
            stage_dates[fixture.stage_id.id].add(date_by_day[day_id])

        reserve, blocked = self._stage_reservations(fixtures)

        # Per-team load per day, the rest limit per day and each team's fair
        # share per day, so no team piles up matches on one day.
        team_load = defaultdict(Counter)
        team_limit = {day["matchday_id"]: day.get("team_limit") or 0 for day in days}
        key_total = Counter()
        key_days = {}
        for fixture in fixtures:
            playable = (
                sum(1 for day in days if allows(day["matchday_id"], fixture)) or 1
            )
            for key in self._team_ids(fixture):
                key_total[key] += 1
                key_days[key] = max(key_days.get(key, 0), playable)
        share = {key: ceil(total / key_days[key]) for key, total in key_total.items()}

        def over_limit(day_id, keys):
            limit = team_limit.get(day_id)
            return bool(limit) and any(
                team_load[day_id][key] + 1 > limit for key in keys
            )

        def over_share(day_id, keys):
            return any(team_load[day_id][key] + 1 > share.get(key, 1) for key in keys)

        def reservation_allows(day_id, fixture, division_days):
            """Keep the last game days free for the stages that follow."""
            stage_id = fixture.stage_id.id
            if day_id in blocked.get(stage_id, ()):
                return False
            keep_free = min(reserve.get(stage_id, 0), max(len(division_days) - 1, 0))
            if not keep_free:
                return True
            usable = [day["matchday_id"] for day in division_days[:-keep_free]]
            return day_id in usable

        unplaced = defaultdict(int)
        unplaced_stage = defaultdict(int)

        for fixture_id, matchday_id in sorted(pinned.items()):
            fixture = fixtures_by_id.get(fixture_id)
            if not fixture or matchday_id not in remaining:
                errors.append(
                    "A pinned fixture or game day is outside the selected scope."
                )
                continue
            if not allows(matchday_id, fixture):
                errors.append(
                    "%s is already planned on a game day where its division does not play."
                    % fixture.display_name
                )
                continue
            if remaining[matchday_id] <= 0:
                errors.append("Pinned fixtures exceed a game day's capacity.")
                continue
            assign(fixture, matchday_id)

        unpinned = fixtures.filtered(lambda fixture: fixture.id not in pinned)
        for fixture in self._ordered(unpinned):
            keys = self._team_ids(fixture)
            all_division_days = [
                day for day in days if allows(day["matchday_id"], fixture)
            ]
            division_days = [
                day for day in all_division_days if remaining[day["matchday_id"]] > 0
            ]
            bound = earliest(fixture)
            candidates = [
                day
                for day in division_days
                if stage_allows(day["matchday_id"], fixture)
                and chronology_allows(day["matchday_id"], bound)
                and reservation_allows(day["matchday_id"], fixture, all_division_days)
            ]
            if not candidates and not self._stage_day_ids(fixture):
                # The reservation is a preference: rather use a reserved day
                # than leave a match of an earlier stage unplanned.
                candidates = [
                    day
                    for day in division_days
                    if chronology_allows(day["matchday_id"], bound)
                    and day["matchday_id"] not in blocked.get(fixture.stage_id.id, ())
                ]
            # Rest is a hard preference: only days where every team of this
            # match still fits with the required rest, when there are any.
            rested = [
                day for day in candidates if not over_limit(day["matchday_id"], keys)
            ]
            if rested:
                candidates = rested
            source_dates = {
                placed_dates.get(source.id)
                for source in (
                    fixture.home_source_fixture_id,
                    fixture.away_source_fixture_id,
                )
                if source
            } - {None}
            cohort = (fixture.stage_id.id, fixture.round_number)
            candidates.sort(
                key=lambda day: (
                    # Spread each team's matches evenly over its game days:
                    # first stay within each team's fair share, then use the
                    # day where the busiest team of this match plays least.
                    over_share(day["matchday_id"], keys),
                    max(
                        (team_load[day["matchday_id"]][key] for key in keys), default=0
                    ),
                    len(keys & team_days[day["matchday_id"]]),
                    # Prefer a later day for a follow-up round when one is free.
                    day["date"] in source_dates,
                    # Keep matches in the same round together when capacity allows.
                    cohort not in round_days[day["matchday_id"]],
                    -remaining[day["matchday_id"]],
                    day["date"],
                    day["matchday_id"],
                )
            )
            if not candidates:
                if division_days:
                    unplaced_stage[fixture.stage_id] += 1
                else:
                    unplaced[fixture.division_id] += 1
                continue
            assign(fixture, candidates[0]["matchday_id"])
        self._repair_rest(
            fixtures,
            pinned,
            days,
            assignments,
            team_load,
            team_limit,
            remaining,
            allows,
            stage_allows,
            placed_dates,
            date_by_day,
        )
        for stage, count in sorted(
            unplaced_stage.items(), key=lambda item: (item[0].sequence, item[0].id)
        ):
            sources = ", ".join(stage._planning_source_stages().mapped("name"))
            if self._stage_day_ids_for_stage(stage):
                errors.append(
                    "%s: %s match(es) do not fit on the game days chosen for this "
                    "stage%s. Add game days to the stage or free capacity on them."
                    % (
                        stage.display_name,
                        count,
                        " after %s ends" % sources if sources else "",
                    )
                )
            else:
                errors.append(
                    "%s: %s match(es) have no game day left after %s ends. Add game "
                    "days at the end of the calendar or courts on the last days."
                    % (stage.display_name, count, sources or "the previous round")
                )
        for division, count in sorted(
            unplaced.items(), key=lambda item: (item[0].display_name or "", item[0].id)
        ):
            playing_days = [
                day
                for day in days
                if allows(day["matchday_id"], _DivisionProbe(division))
            ]
            name = division.display_name or "Division"
            if not playing_days:
                errors.append(
                    "%s has no game day it may play on. Add it to the divisions "
                    "playing of at least one game day." % name
                )
            else:
                errors.append(
                    "%s: %s match(es) do not fit on its %s game day(s). Add game days "
                    "or courts, or let the division play on more game days."
                    % (name, count, len(playing_days))
                )
        return {
            "assignments": dict(assignments),
            "remaining_capacity": remaining,
            "errors": errors,
            "valid": not errors,
        }

    def _repair_rest(
        self,
        fixtures,
        pinned,
        days,
        assignments,
        team_load,
        team_limit,
        remaining,
        allows,
        stage_allows,
        placed_dates,
        date_by_day,
    ):
        """Move single matches off days where a team has more than rest allows.

        The greedy pass can leave a team one match over its limit on a day
        while another day still has room for both teams. Only matches that no
        other match depends on, and that depend on nothing, are moved, so
        stage order and knockout chronology stay untouched.
        """
        by_id = {fixture.id: fixture for fixture in fixtures}
        linked_stage_ids = set()
        depending_fixture_ids = set()
        for fixture in fixtures:
            sources = self._source_stages(fixture)
            if sources:
                linked_stage_ids.add(fixture.stage_id.id)
                linked_stage_ids.update(sources.ids)
            for source in (
                fixture.home_source_fixture_id,
                fixture.away_source_fixture_id,
            ):
                if source:
                    depending_fixture_ids.update((fixture.id, source.id))

        def movable(fixture):
            return (
                fixture.id not in pinned
                and fixture.id not in depending_fixture_ids
                and fixture.stage_id.id not in linked_stage_ids
            )

        def excess(day_id, keys):
            limit = team_limit.get(day_id)
            if not limit:
                return 0
            return sum(max(0, team_load[day_id][key] - limit) for key in keys)

        def fits(day_id, fixture):
            return allows(day_id, fixture) and stage_allows(day_id, fixture)

        def relocate(fixture_id, keys, source_id, target_id):
            assignments[source_id].remove(fixture_id)
            assignments[target_id].append(fixture_id)
            remaining[source_id] += 1
            remaining[target_id] -= 1
            team_load[source_id].subtract(keys)
            team_load[target_id].update(keys)
            placed_dates[fixture_id] = date_by_day[target_id]

        def try_improve(fixture, keys, day_id):
            """Move the match, or swap it with one on another day, when that
            lowers the number of matches over the rest limit."""
            for other in days:
                other_id = other["matchday_id"]
                if other_id == day_id or not fits(other_id, fixture):
                    continue
                touched = keys
                before = excess(day_id, touched) + excess(other_id, touched)
                if remaining[other_id] > 0:
                    relocate(fixture.id, keys, day_id, other_id)
                    if excess(day_id, touched) + excess(other_id, touched) < before:
                        return True
                    relocate(fixture.id, keys, other_id, day_id)
                for partner_id in list(assignments.get(other_id, [])):
                    partner = by_id.get(partner_id)
                    if not partner or not movable(partner) or not fits(day_id, partner):
                        continue
                    partner_keys = self._team_ids(partner)
                    touched = keys | partner_keys
                    before = excess(day_id, touched) + excess(other_id, touched)
                    relocate(fixture.id, keys, day_id, other_id)
                    relocate(partner_id, partner_keys, other_id, day_id)
                    if excess(day_id, touched) + excess(other_id, touched) < before:
                        return True
                    relocate(partner_id, partner_keys, day_id, other_id)
                    relocate(fixture.id, keys, other_id, day_id)
            return False

        for _round in range(4):
            moved = False
            for day in days:
                day_id = day["matchday_id"]
                if not team_limit.get(day_id):
                    continue
                for fixture_id in list(assignments.get(day_id, [])):
                    fixture = by_id.get(fixture_id)
                    if (
                        not fixture
                        or fixture_id not in assignments.get(day_id, [])
                        or not movable(fixture)
                    ):
                        continue
                    keys = self._team_ids(fixture)
                    if excess(day_id, keys) and try_improve(fixture, keys, day_id):
                        moved = True
            if not moved:
                break

    def _stage_reservations(self, fixtures):
        """Game days earlier stages leave free for the stages they feed.

        A stage keeps as many of its division's last game days free as the
        rounds of the stages that follow it (a split season with 5 rounds
        after the regular season keeps the last 5 days free). Stages that
        follow on chosen game days keep exactly those days free instead.
        Returns ``(reserve_by_stage_id, blocked_day_ids_by_stage_id)``.
        """
        stages = {}
        rounds = defaultdict(set)
        for fixture in fixtures:
            stages[fixture.stage_id.id] = fixture.stage_id
            rounds[fixture.stage_id.id].add(fixture.round_number)
        dependants = defaultdict(list)
        for stage in stages.values():
            for source in self._source_stages(stage_fixture_probe(stage)):
                dependants[source.id].append(stage)
        reserve, blocked = {}, defaultdict(set)

        def needed(stage_id, trail=()):
            if stage_id in reserve:
                return reserve[stage_id]
            if stage_id in trail:
                return 0
            value = 0
            for target in dependants.get(stage_id, ()):
                windows = self._stage_day_ids_for_stage(target)
                if windows:
                    blocked[stage_id] |= windows
                    continue
                value = max(
                    value,
                    len(rounds.get(target.id, ()))
                    + needed(target.id, trail + (stage_id,)),
                )
            reserve[stage_id] = value
            return value

        for stage_id in list(stages):
            needed(stage_id)
        for stage_id, stage in stages.items():
            # A stage limited to its own game days may use them all.
            own = self._stage_day_ids_for_stage(stage)
            if own:
                reserve[stage_id] = 0
                blocked[stage_id] -= own
        return reserve, blocked

    def distribute(self, fixtures, capacities):
        """Compatibility wrapper for the original competition wizard."""
        proposal = self.propose(fixtures, capacities)
        if proposal["errors"]:
            from odoo.exceptions import ValidationError

            raise ValidationError("\n".join(proposal["errors"]))
        return proposal

    def _assign(self, fixture, day_id, assignments, team_days, remaining):
        assignments[day_id].append(fixture.id)
        remaining[day_id] -= 1
        team_days[day_id].update(self._team_ids(fixture))

    def _team_ids(self, fixture):
        """Participants, with stable tokens for not-yet-known teams.

        Placeholder sides ("#1 Group A") count as participants so a stage
        planned in advance is still spread over its game days by round.
        """
        planning_keys = getattr(fixture, "_planning_keys", None)
        if planning_keys:
            return planning_keys()
        return {fixture.home_team_id.id, fixture.away_team_id.id} - {False}

    def _ordered(self, fixtures):
        planning_sorted = getattr(fixtures, "_planning_sorted", None)
        if planning_sorted:
            return planning_sorted()
        return fixtures.sorted(
            key=lambda fixture: (fixture.round_number, fixture.sequence, fixture.id)
        )

    def _source_stages(self, fixture):
        stage = fixture.stage_id
        getter = getattr(stage, "_planning_source_stages", None)
        return getter() if getter else stage.browse()

    def _stage_day_ids_for_stage(self, stage):
        return set(stage.matchday_ids.ids) if "matchday_ids" in stage._fields else set()

    def _stage_day_ids(self, fixture):
        return self._stage_day_ids_for_stage(fixture.stage_id)


def stage_fixture_probe(stage):
    """Minimal fixture stand-in to ask a stage for its source stages."""
    return _StageProbe(stage)


class _StageProbe:
    def __init__(self, stage):
        self.stage_id = stage


class _DivisionProbe:
    """Minimal fixture stand-in to ask whether a game day allows a division."""

    def __init__(self, division):
        self.division_id = division
