"""Read-only proposal calculation and validation for the competition scheduler."""
import hashlib
import json

from odoo import _, models
from odoo.exceptions import ValidationError

from ..services.rest_capacity import max_matches_with_rest, time_rows


class FederationCompetitionScheduleProposal(models.TransientModel):
    _inherit = "federation.competition.schedule.wizard"

    def _build_proposal(self, require_generated=False):
        errors, warnings = self._validate_scope(require_generated)
        fixtures, deferred, excluded = self._fixtures()
        capacities = self._capacities(errors)
        distribution = self.env["federation.competition.schedule.distributor"].propose(
            fixtures, capacities, pinned=self._pinned_fixture_days(),
            known_days=self._known_fixture_dates(),
        ) if capacities else {"assignments": {}, "remaining_capacity": {}, "errors": [], "valid": False}
        errors.extend(distribution["errors"])
        duplicate_team_days = self._duplicate_team_days(fixtures, distribution)
        rest_shortfalls = self._rest_shortfalls(fixtures, distribution)
        warnings.extend(rest_shortfalls)
        total_capacity = sum(day["capacity"] for day in capacities)
        if len(fixtures) > total_capacity:
            errors.append(
                _("Selected stages contain %(fixtures)s playable fixtures but the selected game days provide only %(slots)s slots.")
                % {"fixtures": len(fixtures), "slots": total_capacity}
            )
        allocation_report = [
            {
                "matchday_id": day["matchday_id"],
                "date": day["date"],
                "capacity": day["capacity"],
                "included_fixture_count": len(
                    distribution["assignments"].get(day["matchday_id"], [])
                ),
                "remaining_capacity": distribution["remaining_capacity"].get(
                    day["matchday_id"], day["capacity"]
                ),
            }
            for day in capacities
        ]
        return {
            "errors": errors,
            "warnings": warnings,
            "distribution": distribution,
            "feasibility": {
                "fixture_count": len(fixtures),
                "included_fixture_count": len(fixtures),
                "excluded_fixture_count": len(excluded),
                "selected_stage_count": len(self.stage_ids),
                "deferred_fixture_count": len(deferred),
                "available_slot_count": total_capacity,
                "capacity_surplus": total_capacity - len(fixtures),
                "game_days": capacities,
                "errors": errors,
            },
            "allocation_report": allocation_report,
            "quality": {
                "warnings": warnings,
                "teams_with_multiple_same_day_matches": duplicate_team_days,
                "rest_shortfalls": rest_shortfalls,
                "planned_fixture_counts": {
                    str(day_id): len(ids) for day_id, ids in distribution["assignments"].items()
                },
                "remaining_capacity": distribution["remaining_capacity"],
            },
        }

    def _validate_scope(self, require_generated=False):
        errors, warnings = [], []
        if not self.matchday_ids or not self.structure_ids:
            errors.append(_("Select competition formats and game days."))
        if self.stage_ids and self.stage_ids.filtered(
            lambda stage: stage.structure_id not in self.structure_ids
        ):
            errors.append(_("Every selected stage must belong to a selected competition format."))
        if len(self.stage_ids) > 1:
            warnings.append(
                _("This preview mixes %(count)s competition stages. Review the per-day allocation before applying it.")
                % {"count": len(self.stage_ids)}
            )
        selected_fixtures = self.structure_ids.mapped("fixture_ids")
        if self.stage_ids:
            selected_fixtures = selected_fixtures.filtered(
                lambda fixture: fixture.stage_id in self.stage_ids
            )
        allocated_days_by_fixture = {}
        for day in self.env["federation.matchday"].search(
            [("edition_id", "=", self.edition_id.id)]
        ):
            for fixture in day.allocation_ids.mapped("fixture_ids") & selected_fixtures:
                allocated_days_by_fixture.setdefault(
                    fixture.id, self.env["federation.matchday"]
                )
                allocated_days_by_fixture[fixture.id] |= day
        for fixture_id, allocated_days in allocated_days_by_fixture.items():
            if len(allocated_days) > 1:
                fixture = selected_fixtures.browse(fixture_id)
                errors.append(
                    _("%(fixture)s is allocated to multiple game days: %(days)s.")
                    % {
                        "fixture": fixture.display_name,
                        "days": ", ".join(
                            allocated_days.sorted("date").mapped("display_name")
                        ),
                    }
                )
        for structure in self.structure_ids:
            if structure.state == "draft" and (require_generated or not self.generate_missing_fixtures):
                errors.append(_("Generate fixtures for %s.") % structure.display_name)
            elif structure.state == "draft":
                warnings.append(_("Fixtures for %s will be generated on apply.") % structure.display_name)
        for day in self.matchday_ids:
            if day.state not in ("draft", "capacity_ready"):
                errors.append(_("%s is no longer mutable.") % day.display_name)
            if not day.planning_court_ids:
                errors.append(_("Select planning courts for %s.") % day.display_name)
            schedules = self.env["federation.schedule"].search([("matchday_id", "=", day.id)])
            if schedules.filtered(lambda schedule: schedule.state not in ("draft", "changes_requested")):
                errors.append(_("%s has reviewed or published planning.") % day.display_name)
            if self.mode == "fill" and (day.slot_ids or day.allocation_ids or schedules):
                warnings.append(_("Existing planning on %s will be retained.") % day.display_name)
        return errors, warnings

    def _fixtures(self):
        all_fixtures = self.structure_ids.mapped("fixture_ids")
        scoped = (
            all_fixtures.filtered(lambda fixture: fixture.stage_id in self.stage_ids)
            if self.stage_ids
            else all_fixtures
        )
        other_days = self.env["federation.matchday"].search(
            [
                ("edition_id", "=", self.edition_id.id),
                ("id", "not in", self.matchday_ids.ids),
            ]
        )
        allocated_elsewhere = other_days.mapped("allocation_ids.fixture_ids")
        scoped -= allocated_elsewhere
        playable = scoped.filtered(lambda fixture: fixture._is_schedulable())
        deferred = scoped - playable
        excluded = all_fixtures - scoped
        return playable, deferred, excluded

    def _known_fixture_dates(self):
        """Dates of fixtures of these formats already on other game days."""
        known = {}
        selected = self.structure_ids.mapped("fixture_ids")
        other_days = self.env["federation.matchday"].search(
            [
                ("edition_id", "=", self.edition_id.id),
                ("id", "not in", self.matchday_ids.ids),
            ]
        )
        for day in other_days:
            for fixture in day.allocation_ids.mapped("fixture_ids") & selected:
                known[fixture.id] = day.date
        return known

    def _capacities(self, errors):
        capacities = []
        generator = self.env["federation.slot.generator"]
        for day in self.matchday_ids.sorted(lambda item: (item.date, item.id)):
            if not day.planning_court_ids:
                continue
            try:
                plan = generator.plan(
                    day, day.planning_court_ids, day.default_day_start_hour,
                    day.default_day_end_hour, day.default_slot_duration_minutes,
                    noon_pause=day.default_noon_pause,
                    noon_pause_minutes=day.default_noon_pause_minutes,
                )
            except ValidationError as exc:
                errors.append("%s: %s" % (day.display_name, exc))
                continue
            retained = len(day.slot_ids.filtered(lambda slot: slot.state == "available")) if self.mode == "fill" else 0
            rows = self._day_time_rows(day)
            capacities.append(
                {"matchday_id": day.id, "date": day.date,
                 "capacity": retained or len(plan["available"]), "blocked": plan["blocked_count"],
                 "division_ids": day.division_ids.ids,
                 # Most matches one team can play on this day with the rest.
                 "team_limit": max_matches_with_rest(rows, self.preferred_rest_minutes) if rows else 0}
            )
        return capacities

    def _pinned_fixture_days(self):
        pinned = {}
        if self.mode == "fill":
            for day in self.matchday_ids:
                for fixture in day.allocation_ids.mapped("fixture_ids"):
                    pinned[fixture.id] = day.id
        return pinned

    def _day_time_rows(self, day):
        """Time rows of the slots this game day will offer."""
        if self.mode == "fill" and day.slot_ids:
            slots = [
                {"start_datetime": slot.start_datetime, "end_datetime": slot.end_datetime}
                for slot in day.slot_ids.filtered(lambda item: item.state == "available")
            ]
        else:
            try:
                slots = self.env["federation.slot.generator"].plan(
                    day, day.planning_court_ids, day.default_day_start_hour,
                    day.default_day_end_hour, day.default_slot_duration_minutes,
                    noon_pause=day.default_noon_pause,
                    noon_pause_minutes=day.default_noon_pause_minutes,
                )["available"]
            except ValidationError:
                return []
        return time_rows(slots)

    def _rest_shortfalls(self, fixtures, distribution):
        """Explain game days where a team has more matches than rest allows.

        Matches are already spread over the game days, so a shortfall left
        here means a team simply has more matches than its game days can hold
        with the required rest. The message says so, with the numbers, while
        the operator can still add time, courts or game days, or lower the rest.
        """
        by_id = {fixture.id: fixture for fixture in fixtures}
        days = self.matchday_ids.sorted(lambda item: (item.date, item.id))
        limits = {}
        for day in days:
            rows = self._day_time_rows(day)
            limits[day.id] = max_matches_with_rest(rows, self.preferred_rest_minutes) if rows else 0
        team_total, team_division = {}, {}
        for fixture in fixtures:
            for team in (fixture.home_team_id, fixture.away_team_id):
                if team:
                    team_total[team] = team_total.get(team, 0) + 1
                    team_division[team] = fixture.division_id

        def season_room(team):
            division = team_division.get(team)
            playing = [
                day for day in days
                if not division or not hasattr(day, "_allows_division") or day._allows_division(division)
            ]
            return len(playing), sum(limits.get(day.id, 0) for day in playing)

        messages = []
        for day in days:
            fixture_ids = distribution["assignments"].get(day.id, [])
            if not fixture_ids:
                continue
            counts = {}
            for fixture_id in fixture_ids:
                fixture = by_id.get(fixture_id)
                if not fixture:
                    continue
                for team in (fixture.home_team_id, fixture.away_team_id):
                    if team:
                        counts[team] = counts.get(team, 0) + 1
            limit = limits.get(day.id)
            if not counts or not limit:
                continue
            crowded = sorted(
                (team for team, count in counts.items() if count > limit),
                key=lambda team: (-counts[team], team.display_name or ""),
            )
            if not crowded:
                continue
            most = counts[crowded[0]]
            names = ", ".join(team.display_name for team in crowded[:3])
            if len(crowded) > 3:
                names += _(" and %(count)s more", count=len(crowded) - 3)
            day_count, room = season_room(crowded[0])
            total = team_total.get(crowded[0], 0)
            if total > room:
                messages.append(
                    _(
                        "%(day)s: %(teams)s play up to %(most)s matches here. %(team)s has "
                        "%(total)s matches, but with %(rest)s minutes rest its %(days)s "
                        "game day(s) fit at most %(room)s. Lower the rest, add time or "
                        "courts, or add game days for this division; otherwise short "
                        "rest must be accepted when publishing.",
                        day=day.display_name,
                        teams=names,
                        most=most,
                        team=crowded[0].display_name,
                        total=total,
                        rest=self.preferred_rest_minutes,
                        days=day_count,
                        room=room,
                    )
                )
                continue
            messages.append(
                _(
                    "%(day)s: %(teams)s play up to %(most)s matches, but with "
                    "%(rest)s minutes rest a team fits at most %(limit)s matches in "
                    "this day, even with their matches spread over every game day "
                    "they can play on. Lower the rest, add time or courts, or add "
                    "game days for these divisions; otherwise short rest must be "
                    "accepted when publishing.",
                    day=day.display_name,
                    teams=names,
                    most=most,
                    rest=self.preferred_rest_minutes,
                    limit=limit,
                )
            )
        return messages

    def _duplicate_team_days(self, fixtures, distribution):
        by_id = {fixture.id: fixture for fixture in fixtures}
        total = 0
        for fixture_ids in distribution["assignments"].values():
            counts = {}
            for fixture_id in fixture_ids:
                fixture = by_id[fixture_id]
                for team in (fixture.home_team_id, fixture.away_team_id):
                    if team:
                        counts[team.id] = counts.get(team.id, 0) + 1
            total += sum(1 for count in counts.values() if count > 1)
        return total

    def _input_signature(self):
        payload = {
            "edition": self.edition_id.id,
            "structures": [(item.id, item.state, item.version, item.write_date) for item in self.structure_ids],
            "stages": [(stage.id, stage.graph_state, stage.write_date) for stage in self.stage_ids],
            "stage_days": [
                (stage.id, sorted(stage.matchday_ids.ids))
                for stage in self.structure_ids.mapped("stage_ids")
            ],
            "days": [(day.id, day.state, day.date, day.default_day_start_hour,
                      day.default_day_end_hour, day.default_slot_duration_minutes,
                      day.planning_court_ids.ids, day.write_date) for day in self.matchday_ids],
            "mode": self.mode,
        }
        return hashlib.sha256(json.dumps(payload, default=str, sort_keys=True).encode()).hexdigest()
