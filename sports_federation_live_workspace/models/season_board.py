"""Season match board: every match of a competition on every game day.

The board shows the matches that still need a game day and a time slot,
next to a court-by-time grid per game day. A match is moved by placing it on
a slot (drag-and-drop or click), on a game day (first fitting slot), or back
to the list. Moves apply immediately and can be undone; they are refused
when they would add a schedule error.

Only working schedules (draft or changes requested) of open game days can
change. Published schedules stay protected and are amended through the
existing revision flow.
"""

import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

CLOSED_DAY_STATES = ("open", "closed", "cancelled")
BOARD_REASON = "Season board"
MAX_BATCH = 200


class _BoardRejected(Exception):
    def __init__(self, errors):
        super().__init__("board change rejected")
        self.errors = errors


class FederationSeasonBoard(models.AbstractModel):
    _name = "federation.season.board"
    _description = "Season Match Board"

    # ------------------------------------------------------------------
    # Scope and access
    # ------------------------------------------------------------------
    @api.model
    def _edition(self, edition_id, mutable=False):
        edition = (
            self.env["federation.competition.edition"]
            .browse(int(edition_id or 0))
            .exists()
        )
        if not edition:
            raise ValidationError(_("Choose an existing competition."))
        edition.check_access("read")
        roles = ["schedule_planner", "competition_director"]
        if not mutable:
            roles.append("schedule_approver")
        self.env["federation.competition.role.assignment"].assert_role(edition, *roles)
        return edition

    @api.model
    def _can_edit(self, edition):
        try:
            self.env["federation.competition.role.assignment"].assert_role(
                edition, "schedule_planner", "competition_director"
            )
            self.env["federation.schedule"].check_access("write")
        except Exception:  # noqa: BLE001 - any refusal means read-only
            return False
        return True

    @api.model
    def _days(self, edition):
        return self.env["federation.matchday"].search(
            [("edition_id", "=", edition.id), ("state", "!=", "cancelled")],
            order="date,id",
        )

    @api.model
    def _active_schedule(self, day):
        return self.env["federation.schedule"].search(
            [("matchday_id", "=", day.id), ("state", "!=", "superseded")], limit=1
        )

    @api.model
    def _structures(self, edition):
        """Latest generated format of every division."""
        structures = self.env["federation.competition.structure"].search(
            [("edition_id", "=", edition.id), ("state", "in", ("generated", "frozen"))],
            order="division_id,version desc,id desc",
        )
        latest = {}
        for structure in structures:
            latest.setdefault(structure.division_id.id, structure)
        return self.env["federation.competition.structure"].browse(
            [structure.id for structure in latest.values()]
        )

    @api.model
    def _fixtures(self, edition):
        """Matches that can be planned: real or placeholder, never byes."""
        return (
            self._structures(edition)
            .mapped("fixture_ids")
            .filtered(
                lambda fixture: fixture.state in ("ready", "completed")
                and not fixture.bye_team_id
                and fixture._is_schedulable()
            )
        )

    @api.model
    def _day_lock(self, day, schedule):
        """Why a game day cannot change, or False."""
        if day.state in CLOSED_DAY_STATES:
            return _(
                "This game day is %s.",
                dict(day._fields["state"].selection).get(day.state),
            )
        if schedule and schedule.state not in schedule._MUTABLE_STATES:
            return _("The schedule is %s. Amend it to change matches.") % dict(
                schedule._fields["state"].selection
            ).get(schedule.state)
        return False

    @api.model
    def _locate(self, edition, fixtures):
        """Current game day, schedule and slot of every fixture."""
        positions = {
            fixture.id: {"day": False, "schedule": False, "slot": False}
            for fixture in fixtures
        }
        for day in self._days(edition):
            schedule = self._active_schedule(day)
            for fixture in day.allocation_ids.mapped("fixture_ids"):
                if fixture.id in positions:
                    positions[fixture.id].update(day=day, schedule=schedule)
            for assignment in schedule.assignment_ids:
                if assignment.fixture_id.id in positions:
                    positions[assignment.fixture_id.id].update(
                        day=day, schedule=schedule, slot=assignment.slot_id
                    )
        return positions

    @api.model
    def _signature(self, edition):
        days = self._days(edition)
        schedules = self.env["federation.schedule"].search(
            [("edition_id", "=", edition.id), ("state", "!=", "superseded")]
        )
        payload = {
            "days": [
                (day.id, day.state, len(day.slot_ids), str(day.write_date))
                for day in days
            ],
            "allocations": sorted(
                (
                    allocation.id,
                    str(allocation.write_date),
                    sorted(allocation.manual_fixture_ids.ids),
                )
                for allocation in days.mapped("allocation_ids")
            ),
            "schedules": sorted((s.id, s.state, s.revision) for s in schedules),
            "structures": sorted((s.id, s.state) for s in self._structures(edition)),
        }
        return hashlib.sha256(
            json.dumps(payload, default=str, sort_keys=True).encode()
        ).hexdigest()

    # ------------------------------------------------------------------
    # Read model
    # ------------------------------------------------------------------
    @api.model
    def _side(self, fixture, side):
        return (
            fixture._side_label(side)
            if hasattr(fixture, "_side_label")
            else (fixture["%s_team_id" % side].display_name or _("TBD"))
        )

    @api.model
    def _issues(self, schedule):
        """Errors and warnings of one schedule, keyed by fixture id."""
        result = {"errors": {}, "warnings": {}, "general": []}
        if not schedule or not schedule.assignment_ids:
            return result
        validation = self.env["federation.schedule.validator"].validate_map(
            schedule, {a.fixture_id.id: a.slot_id.id for a in schedule.assignment_ids}
        )
        by_slot = {a.slot_id.id: a.fixture_id.id for a in schedule.assignment_ids}
        for kind in ("errors", "warnings"):
            for issue in validation[kind]:
                fixture_id = issue.get("fixture_id") or by_slot.get(
                    issue.get("slot_id")
                )
                if fixture_id:
                    result[kind].setdefault(fixture_id, []).append(issue["message"])
                elif kind == "errors":
                    result["general"].append(issue["message"])
        return result

    @api.model
    def load(self, edition_id):
        edition = self._edition(edition_id)
        fixtures = self._fixtures(edition)
        positions = self._locate(edition, fixtures)
        editable = self._can_edit(edition)
        days, errors, warnings, general = [], {}, {}, []
        for day in self._days(edition):
            schedule = self._active_schedule(day)
            lock = self._day_lock(day, schedule)
            issues = self._issues(schedule)
            errors.update(issues["errors"])
            warnings.update(issues["warnings"])
            general.extend(
                "%s: %s" % (day.display_name, message) for message in issues["general"]
            )
            slots = day.slot_ids.sorted(
                lambda slot: (
                    slot.start_datetime,
                    (
                        slot.court_id.sequence
                        if "sequence" in slot.court_id._fields
                        else 0
                    ),
                    slot.court_id.id,
                    slot.id,
                )
            )
            courts = slots.mapped("court_id") or day.planning_court_ids
            days.append(
                {
                    "id": day.id,
                    "name": day.display_name,
                    "date": fields.Date.to_string(day.date),
                    "state": day.state,
                    "venue": day.venue_id.display_name or "",
                    "timezone": day.event_timezone or "UTC",
                    "schedule_id": schedule.id or False,
                    "schedule_state": schedule.state or False,
                    "locked": bool(lock) or not editable,
                    "lock_reason": lock
                    or (
                        False
                        if editable
                        else _("You can view this plan but not change it.")
                    ),
                    "division_ids": (
                        day.division_ids.ids if "division_ids" in day._fields else []
                    ),
                    "courts": [
                        {"id": court.id, "name": court.display_name} for court in courts
                    ],
                    "slots": [
                        {
                            "id": slot.id,
                            "court_id": slot.court_id.id,
                            "start": fields.Datetime.to_string(slot.start_datetime),
                            "end": fields.Datetime.to_string(slot.end_datetime),
                            "state": slot.state,
                        }
                        for slot in slots
                    ],
                    "playable_slots": len(
                        slots.filtered(lambda slot: slot.state == "available")
                    ),
                    "can_generate_slots": bool(
                        editable
                        and not lock
                        and not slots
                        and day.planning_court_ids
                        and day.state in ("draft", "capacity_ready")
                    ),
                    "needs_courts": not slots and not day.planning_court_ids,
                }
            )
        stage_names = {}
        rows = []
        for fixture in fixtures.sorted(
            lambda f: (
                f.division_id.name or "",
                f.stage_id.sequence,
                f.round_number,
                f.sequence,
                f.id,
            )
        ):
            position = positions[fixture.id]
            stage = fixture.stage_id
            stage_names.setdefault(
                stage.id,
                {
                    "id": stage.id,
                    "name": stage.name,
                    "division_id": fixture.division_id.id,
                },
            )
            assignment = (
                position["schedule"].assignment_ids.filtered(
                    lambda item: item.fixture_id == fixture
                )[:1]
                if position["schedule"]
                else False
            )
            rows.append(
                {
                    "id": fixture.id,
                    "home": self._side(fixture, "home"),
                    "away": self._side(fixture, "away"),
                    "division_id": fixture.division_id.id,
                    "division": fixture.division_id.display_name,
                    "stage_id": stage.id,
                    "stage": stage.name,
                    "round": fixture.round_number,
                    "teams": [
                        team.id
                        for team in (fixture.home_team_id | fixture.away_team_id)
                    ],
                    "placeholder": not (fixture.home_team_id and fixture.away_team_id),
                    "completed": fixture.state == "completed",
                    "day_id": position["day"].id if position["day"] else False,
                    "slot_id": position["slot"].id if position["slot"] else False,
                    "pinned": bool(assignment and assignment.method == "manual"),
                    "errors": errors.get(fixture.id, []),
                    "warnings": warnings.get(fixture.id, []),
                }
            )
        divisions = fixtures.mapped("division_id").sorted(
            lambda d: (d.name or "", d.id)
        )
        return {
            "edition": {"id": edition.id, "name": edition.display_name},
            "signature": self._signature(edition),
            "editable": editable,
            "days": days,
            "fixtures": rows,
            "divisions": [{"id": d.id, "name": d.display_name} for d in divisions],
            "stages": list(stage_names.values()),
            "general_errors": general,
            "unplanned_count": sum(1 for row in rows if not row["slot_id"]),
            "error_count": sum(1 for row in rows if row["errors"]),
        }

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------
    @api.model
    def _check_signature(self, edition, signature):
        if signature != self._signature(edition):
            raise ValidationError(
                _(
                    "Someone else changed this plan. The board has been refreshed; try again."
                )
            )

    @api.model
    def _ensure_schedule(self, day, structure):
        schedule = self._active_schedule(day)
        if schedule:
            return schedule
        return self.env["federation.schedule"].create(
            {
                "name": _("%s schedule") % day.display_name,
                "edition_id": day.edition_id.id,
                "structure_id": structure.id,
                "matchday_id": day.id,
            }
        )

    @api.model
    def _remove_from_day(self, day, fixture):
        for allocation in day.allocation_ids:
            if fixture not in allocation.fixture_ids:
                continue
            remaining = allocation.fixture_ids - fixture
            if not remaining:
                allocation.unlink()
            elif allocation.manual_only:
                allocation.manual_fixture_ids = [fields.Command.unlink(fixture.id)]
            else:
                # A round or stage allocation becomes an explicit list without
                # this match, so the rest of the round stays on this day.
                allocation.write(
                    {
                        "manual_only": True,
                        "manual_fixture_ids": [fields.Command.set(remaining.ids)],
                    }
                )

    @api.model
    def _add_to_day(self, day, fixture):
        if fixture in day.allocation_ids.mapped("fixture_ids"):
            return
        allocation = day.allocation_ids.filtered(
            lambda item: item.structure_id == fixture.structure_id and item.manual_only
        )[:1]
        if allocation:
            allocation.manual_fixture_ids = [fields.Command.link(fixture.id)]
        else:
            self.env["federation.matchday.allocation"].create(
                {
                    "matchday_id": day.id,
                    "structure_id": fixture.structure_id.id,
                    "manual_only": True,
                    "manual_fixture_ids": [fields.Command.set(fixture.ids)],
                }
            )

    @api.model
    def _validation_keys(self, schedule):
        validation = self.env["federation.schedule.validator"].validate_map(
            schedule, {a.fixture_id.id: a.slot_id.id for a in schedule.assignment_ids}
        )
        return {
            (
                issue.get("code"),
                issue.get("fixture_id"),
                issue.get("slot_id"),
                issue["message"],
            )
            for issue in validation["errors"]
        }

    @api.model
    def _apply_positions(self, edition, targets, method="manual"):
        """Put fixtures on slots (or back in the list) in one checked change.

        ``targets`` maps fixture ids to a slot id, or False for "not planned".
        Returns ``(changes, errors)``. When the change would add a schedule
        error nothing is changed and the errors are returned.
        """
        Fixture = self.env["federation.fixture"]
        Day = self.env["federation.matchday"]
        fixtures = Fixture.browse(list(targets)).exists()
        if len(fixtures) != len(targets) or fixtures - self._fixtures(edition):
            raise ValidationError(_("Choose matches of this competition."))
        played = fixtures.filtered(lambda fixture: fixture.state == "completed")
        if played:
            raise ValidationError(
                _("%s is already played and keeps its slot.", played[0].display_name)
            )
        slot_ids = [slot_id for slot_id in targets.values() if slot_id]
        if len(set(slot_ids)) != len(slot_ids):
            raise ValidationError(_("Two matches cannot share one time slot."))
        slots = self.env["federation.schedule.slot"].browse(slot_ids).exists()
        if len(slots) != len(slot_ids) or slots.filtered(
            lambda slot: slot.matchday_id.edition_id != edition
        ):
            raise ValidationError(_("Choose a time slot of this competition."))
        slot_by_id = {slot.id: slot for slot in slots}
        positions = self._locate(edition, fixtures)

        source_days, target_days = Day, Day
        for fixture in fixtures:
            current, target = positions[fixture.id], slot_by_id.get(targets[fixture.id])
            if current["day"] and current["slot"] != target:
                source_days |= current["day"]
            if target:
                target_days |= target.matchday_id
                divisions = (
                    target.matchday_id.division_ids
                    if "division_ids" in Day._fields
                    else Day
                )
                if divisions and fixture.division_id not in divisions:
                    raise ValidationError(
                        _(
                            "%(division)s does not play on %(day)s.",
                            division=fixture.division_id.display_name,
                            day=target.matchday_id.display_name,
                        )
                    )
        days = source_days | target_days
        for day in days:
            lock = self._day_lock(day, self._active_schedule(day))
            if lock:
                raise ValidationError("%s: %s" % (day.display_name, lock))

        changes = []
        try:
            with self.env.cr.savepoint():
                schedules = self.env["federation.schedule"]
                for day in target_days:
                    schedules |= self._ensure_schedule(day, fixtures[:1].structure_id)
                for day in source_days - target_days:
                    schedules |= self._active_schedule(day)
                before = {
                    schedule.id: self._validation_keys(schedule)
                    for schedule in schedules
                }
                revisions = {}
                for schedule in schedules:
                    revisions[schedule.id] = self.env[
                        "federation.schedule.commands"
                    ]._resolve(schedule.id, schedule.revision)[1]
                schedule_by_day = {
                    schedule.matchday_id.id: schedule for schedule in schedules
                }
                # Detach everything first so swaps never collide on a slot.
                for fixture in fixtures:
                    current, target = positions[fixture.id], slot_by_id.get(
                        targets[fixture.id]
                    )
                    if current["schedule"]:
                        current["schedule"].assignment_ids.filtered(
                            lambda item: item.fixture_id == fixture
                        ).unlink()
                    if current["day"] and (
                        not target or target.matchday_id != current["day"]
                    ):
                        self._remove_from_day(current["day"], fixture)
                Change = self.env["federation.schedule.change"]
                for fixture in fixtures:
                    current, target = positions[fixture.id], slot_by_id.get(
                        targets[fixture.id]
                    )
                    if target:
                        self._add_to_day(target.matchday_id, fixture)
                        self.env["federation.schedule.assignment"].create(
                            {
                                "schedule_id": schedule_by_day[
                                    target.matchday_id.id
                                ].id,
                                "fixture_id": fixture.id,
                                "slot_id": target.id,
                                "method": method,
                            }
                        )
                    changes.append(
                        {
                            "fixture_id": fixture.id,
                            "from_slot": (
                                current["slot"].id if current["slot"] else False
                            ),
                            "from_day": current["day"].id if current["day"] else False,
                            "to_slot": target.id if target else False,
                        }
                    )
                    touched = {
                        current["day"].id if current["day"] else False,
                        target.matchday_id.id if target else False,
                    } - {False}
                    for day_id in touched:
                        schedule = schedule_by_day.get(day_id)
                        if not schedule:
                            continue
                        Change.create(
                            {
                                "schedule_id": schedule.id,
                                "revision": revisions[schedule.id],
                                "command": "board_move",
                                "fixture_id": fixture.id,
                                "old_slot_id": (
                                    current["slot"].id
                                    if current["slot"]
                                    and current["slot"].matchday_id.id == day_id
                                    else False
                                ),
                                "new_slot_id": (
                                    target.id
                                    if target and target.matchday_id.id == day_id
                                    else False
                                ),
                                "reason": BOARD_REASON,
                            }
                        )
                self.env.flush_all()
                self.env.invalidate_all()
                new_errors = []
                for schedule in schedules:
                    added = self._validation_keys(schedule) - before[schedule.id]
                    new_errors.extend(item[3] for item in sorted(added, key=str))
                if new_errors:
                    raise _BoardRejected(new_errors)
                for day in target_days:
                    if day.state == "draft" and day.slot_ids and day.allocation_ids:
                        day.action_capacity_ready()
        except _BoardRejected as rejected:
            self.env.invalidate_all()
            return [], list(dict.fromkeys(rejected.errors))
        return changes, []

    @api.model
    def _result(self, edition, changes, errors, notice=False):
        data = self.load(edition.id)
        data.update(
            {
                "ok": not errors,
                "changes": changes,
                "rejected": errors,
                "notice": notice or False,
            }
        )
        return data

    @api.model
    def move(self, edition_id, fixture_id, slot_id, signature):
        """Place a match on a slot; a match already there swaps places."""
        edition = self._edition(edition_id, mutable=True)
        self._check_signature(edition, signature)
        fixture = self.env["federation.fixture"].browse(int(fixture_id)).exists()
        slot = self.env["federation.schedule.slot"].browse(int(slot_id)).exists()
        if not fixture or not slot:
            raise ValidationError(_("Choose a match and a time slot."))
        if slot.state != "available":
            raise ValidationError(_("This time slot is not playable."))
        position = self._locate(edition, fixture)[fixture.id]
        if position["slot"] == slot:
            return self._result(edition, [], [])
        targets = {fixture.id: slot.id}
        schedule = self._active_schedule(slot.matchday_id)
        occupant = (
            schedule.assignment_ids.filtered(
                lambda item: item.slot_id == slot
            ).fixture_id
            if schedule
            else False
        )
        if occupant and occupant != fixture:
            targets[occupant.id] = position["slot"].id if position["slot"] else False
        changes, errors = self._apply_positions(edition, targets)
        return self._result(edition, changes, errors)

    @api.model
    def unplan(self, edition_id, fixture_ids, signature):
        """Take matches off their game day and back to the list."""
        edition = self._edition(edition_id, mutable=True)
        self._check_signature(edition, signature)
        ids = [int(value) for value in (fixture_ids or [])][:MAX_BATCH]
        changes, errors = self._apply_positions(edition, {fid: False for fid in ids})
        return self._result(edition, changes, errors)

    @api.model
    def restore(self, edition_id, changes, signature):
        """Undo: put matches back where they were before a board change."""
        edition = self._edition(edition_id, mutable=True)
        self._check_signature(edition, signature)
        targets = {}
        for change in (changes or [])[:MAX_BATCH]:
            targets[int(change["fixture_id"])] = (
                int(change["from_slot"]) if change.get("from_slot") else False
            )
        if not targets:
            return self._result(edition, [], [])
        changes, errors = self._apply_positions(edition, targets)
        return self._result(
            edition,
            changes,
            errors,
            notice=_("Change undone.") if not errors else False,
        )

    @api.model
    def _free_slots(self, day, taken):
        return day.slot_ids.filtered(
            lambda slot: slot.state == "available" and slot.id not in taken
        ).sorted(lambda slot: (slot.start_datetime, slot.court_id.id, slot.id))

    @api.model
    def place_on_day(self, edition_id, fixture_ids, day_id, signature):
        """Put matches on the first fitting free slots of one game day."""
        edition = self._edition(edition_id, mutable=True)
        self._check_signature(edition, signature)
        day = self.env["federation.matchday"].browse(int(day_id)).exists()
        if not day or day.edition_id != edition:
            raise ValidationError(_("Choose a game day of this competition."))
        if not day.slot_ids:
            raise ValidationError(
                _("%s has no time slots yet. Create them first.", day.display_name)
            )
        lock = self._day_lock(day, self._active_schedule(day))
        if lock:
            raise ValidationError("%s: %s" % (day.display_name, lock))
        fixtures = (
            self.env["federation.fixture"]
            .browse([int(value) for value in (fixture_ids or [])][:MAX_BATCH])
            .exists()
        )
        divisions = day.division_ids if "division_ids" in day._fields else False
        placed, skipped, all_changes = 0, [], []
        for fixture in fixtures:
            if divisions and fixture.division_id not in divisions:
                skipped.append(fixture.display_name)
                continue
            schedule = self._active_schedule(day)
            taken = (
                set(schedule.assignment_ids.mapped("slot_id").ids)
                if schedule
                else set()
            )
            # Skip slots where one of the teams already plays: they can never fit.
            teams = fixture.home_team_id | fixture.away_team_id
            busy = [
                (assignment.slot_id.start_datetime, assignment.slot_id.end_datetime)
                for assignment in (schedule.assignment_ids if schedule else [])
                if teams
                & (
                    assignment.fixture_id.home_team_id
                    | assignment.fixture_id.away_team_id
                )
            ]
            candidates = self._free_slots(day, taken).filtered(
                lambda slot: not any(
                    slot.start_datetime < end and start < slot.end_datetime
                    for start, end in busy
                )
            )
            done = False
            for slot in candidates:
                changes, errors = self._apply_positions(
                    edition, {fixture.id: slot.id}, method="automatic"
                )
                if not errors:
                    all_changes.extend(changes)
                    placed += 1
                    done = True
                    break
            if not done:
                skipped.append(fixture.display_name)
        notice = _(
            "%(placed)s of %(total)s match(es) placed on %(day)s.",
            placed=placed,
            total=len(fixtures),
            day=day.display_name,
        )
        if skipped:
            notice += " " + _("No fitting slot for: %s.", ", ".join(skipped[:5]))
        return self._result(edition, all_changes, [], notice=notice)

    @api.model
    def set_pinned(self, edition_id, fixture_id, pinned, signature):
        """Pinned matches keep their slot when planning runs automatically."""
        edition = self._edition(edition_id, mutable=True)
        self._check_signature(edition, signature)
        fixture = self.env["federation.fixture"].browse(int(fixture_id)).exists()
        position = self._locate(edition, fixture)[fixture.id] if fixture else {}
        schedule = position.get("schedule")
        if not schedule or not position.get("slot"):
            raise ValidationError(_("Only a match on a time slot can be pinned."))
        lock = self._day_lock(schedule.matchday_id, schedule)
        if lock:
            raise ValidationError(lock)
        with self.env.cr.savepoint():
            self.env["federation.schedule.commands"]._resolve(
                schedule.id, schedule.revision
            )
            schedule.assignment_ids.filtered(
                lambda item: item.fixture_id == fixture
            ).write({"method": "manual" if pinned else "automatic"})
        return self._result(edition, [], [])

    @api.model
    def generate_slots(self, edition_id, day_id, signature):
        """Create the time slots of a game day from its courts and hours."""
        edition = self._edition(edition_id, mutable=True)
        self._check_signature(edition, signature)
        day = self.env["federation.matchday"].browse(int(day_id)).exists()
        if not day or day.edition_id != edition:
            raise ValidationError(_("Choose a game day of this competition."))
        if day.slot_ids:
            raise ValidationError(_("%s already has time slots.", day.display_name))
        if day.state not in ("draft", "capacity_ready"):
            raise ValidationError(
                _("Time slots can only be created before the game day is scheduled.")
            )
        if not day.planning_court_ids:
            raise ValidationError(_("Choose the courts of %s first.", day.display_name))
        self.env["federation.slot.generator"].generate_plan(
            day,
            day.planning_court_ids,
            day.default_day_start_hour,
            day.default_day_end_hour,
            day.default_slot_duration_minutes,
            noon_pause=day.default_noon_pause,
            noon_pause_minutes=day.default_noon_pause_minutes,
        )
        return self._result(
            edition, [], [], notice=_("Time slots created for %s.", day.display_name)
        )

    @api.model
    def auto_plan_action(self, edition_id):
        """Plan every remaining match with the competition planner (fill mode)."""
        edition = self._edition(edition_id, mutable=True)
        wizard = self.env["federation.competition.schedule.wizard"].create(
            {"edition_id": edition.id, "mode": "fill"}
        )
        wizard._onchange_edition_id()
        return {
            "type": "ir.actions.act_window",
            "name": _("Plan remaining matches"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "new",
        }

    @api.model
    def open_day_schedule(self, edition_id, day_id):
        """The day's schedule form: submit, publish or amend it there."""
        edition = self._edition(edition_id)
        day = self.env["federation.matchday"].browse(int(day_id)).exists()
        if not day or day.edition_id != edition:
            raise ValidationError(_("Choose a game day of this competition."))
        schedule = self._active_schedule(day)
        if schedule:
            return schedule.get_formview_action()
        return day.get_formview_action()


class FederationCompetitionEditionSeasonBoard(models.Model):
    _inherit = "federation.competition.edition"

    def action_open_season_board(self):
        self.ensure_one()
        self.check_access("read")
        return {
            "type": "ir.actions.client",
            "tag": "federation_season_board",
            "name": _("Competition match board: %s", self.display_name),
            "params": {"edition_id": self.id},
            "target": "current",
        }

    def action_open_planner_step(self, step):
        """The planner's Schedule step opens the match board."""
        if step == "schedule":
            self.ensure_one()
            self.check_access("read")
            return self.action_open_season_board()
        return super().action_open_planner_step(step)

    def _planner_issue_action(self, issue):
        if issue.get("key") == "unallocated-fixtures" or str(
            issue.get("key", "")
        ).endswith("-missing-schedule"):
            days = self.env["federation.matchday"].search_count(
                [("edition_id", "=", self.id), ("state", "!=", "cancelled")]
            )
            if days:
                return self.action_open_season_board()
        return super()._planner_issue_action(issue)
