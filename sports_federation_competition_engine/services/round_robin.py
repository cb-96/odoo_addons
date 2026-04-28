import logging
from datetime import datetime, timedelta

from odoo import fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class RoundRobinService(models.AbstractModel):
    _name = "federation.round.robin.service"
    _description = "Round Robin Schedule Generation Service"

    def generate(self, tournament, stage, participants, options):
        """
        Generate round-robin match schedule.

        Args:
            tournament: federation.tournament record
            stage: federation.tournament.stage record
            participants: list of federation.tournament.participant records
            options: dict with keys:
                - double_round: bool
                - rounds_count: int (how many full cycles to repeat)
                - schedule_by_round: bool (if True, schedule each round as a time block)
                - round_interval_hours: int (hours between rounds when scheduling by round)
                - start_datetime: datetime or False
                - interval_hours: int (intra-round spacing)
                - venue: str or False
                - overwrite: bool
                - group: federation.tournament.group or False

        Returns:
            list of created federation.match records
        """
        self._validate_inputs(tournament, stage, participants, options)

        if options.get("overwrite"):
            self._clear_existing_matches(stage, options.get("group"))
        else:
            self._check_existing_matches(stage, options.get("group"))

        teams = [p.team_id for p in participants]
        base_rounds = self._generate_pairings(teams, options.get("double_round", False))

        repeats = int(options.get("rounds_count", 1) or 1)
        rounds = []
        for _ in range(repeats):
            rounds.extend(base_rounds)

        matches = self._create_matches(tournament, stage, rounds, options)

        _logger.info(
            "Generated %d round-robin matches for tournament %s, stage %s",
            len(matches), tournament.name, stage.name
        )
        return matches

    def _validate_inputs(self, tournament, stage, participants, options):
        """Validate inputs."""
        if tournament.state not in ("open", "in_progress"):
            raise UserError(_("Tournament must be Open or In Progress to generate matches."))
        if len(participants) < 2:
            raise UserError(_("At least 2 participants are required for round-robin."))

    def _check_existing_matches(self, stage, group):
        """Validate existing matches."""
        domain = [("stage_id", "=", stage.id)]
        if group:
            domain.append(("group_id", "=", group.id))
        existing = self.env["federation.match"].search(domain)
        if existing:
            raise UserError(_(
                "Existing matches found in this stage/group. "
                "Enable overwrite mode to replace them."
            ))

    def _clear_existing_matches(self, stage, group):
        """Clear existing matches."""
        domain = [("stage_id", "=", stage.id)]
        if group:
            domain.append(("group_id", "=", group.id))
        self.env["federation.match"].search(domain).unlink()

    def _generate_pairings(self, teams, double_round):
        """
        Generate round-robin pairings using the circle method.

        The algorithm fixes the first team and rotates the rest.
        For odd participant counts, a bye (False) is added.
        Home/away alternates by round to ensure fairness.
        """
        n = len(teams)
        has_bye = n % 2 == 1
        if has_bye:
            teams = list(teams) + [False]
            n += 1

        rounds_count = n - 1
        half = n // 2
        working = list(teams)
        rounds_list = []

        for round_num in range(rounds_count):
            round_pairs = []
            for i in range(half):
                home = working[i]
                away = working[n - 1 - i]
                if home and away:
                    # Alternate home/away by round for fairness
                    if round_num % 2 == 0:
                        round_pairs.append((home, away))
                    else:
                        round_pairs.append((away, home))
            rounds_list.append(round_pairs)
            # Rotate: keep first fixed, rotate rest clockwise
            working = [working[0]] + [working[-1]] + working[1:-1]

        if double_round:
            # Append reversed rounds to provide return fixtures
            reversed_rounds = []
            for r in rounds_list:
                reversed_rounds.append([(away, home) for (home, away) in r])
            rounds_list.extend(reversed_rounds)

        return rounds_list

    def _get_stage_rounds(self, stage, group=False):
        """Return stage rounds."""
        return self.env["federation.tournament.round"].search(
            [
                ("stage_id", "=", stage.id),
                ("group_id", "=", group.id if group else False),
            ],
            order="sequence asc, id asc",
        )

    def _get_ordered_round_entries(self, round_pairs):
        """Return ordered round entries."""
        entries = []
        for home, away in round_pairs:
            if not home or not away:
                continue
            h_gender = getattr(home, "gender", None)
            a_gender = getattr(away, "gender", None)
            if h_gender == "male" and a_gender == "male":
                gender = "male"
            elif h_gender == "female" and a_gender == "female":
                gender = "female"
            else:
                gender = "mixed"
            entries.append({"home": home, "away": away, "gender": gender})

        male = [entry for entry in entries if entry["gender"] == "male"]
        female = [entry for entry in entries if entry["gender"] == "female"]
        mixed = [entry for entry in entries if entry["gender"] not in ("male", "female")]

        ordered = []
        last = None
        while male or female:
            if last != "male" and male:
                ordered.append(male.pop(0))
                last = "male"
            elif last != "female" and female:
                ordered.append(female.pop(0))
                last = "female"
            elif male:
                ordered.append(male.pop(0))
                last = "male"
            elif female:
                ordered.append(female.pop(0))
                last = "female"
        ordered.extend(mixed)
        return ordered

    def _get_round_records(
        self,
        stage,
        rounds,
        group=False,
        start_dt=False,
        schedule_by_round=False,
        round_interval_hours=24,
        venue_rec=False,
        round_mode="auto",
        requested_rounds=0,
    ):
        """Return round records based on round mode.

        Args:
            round_mode: 'existing' (use only existing), 'auto' (create missing), 'explicit' (create specific count)
            requested_rounds: number of rounds to create in explicit mode
        """
        Round = self.env["federation.tournament.round"]
        existing_rounds = {
            round_record.sequence: round_record
            for round_record in self._get_stage_rounds(stage, group=group)
        }

        # Determine how many rounds we can work with
        if round_mode == "existing":
            # Only use existing gamedays (rounds), but generate ALL matches
            available_rounds = sorted(existing_rounds.keys())
            if not available_rounds:
                raise UserError(_("No existing rounds found. Use 'Auto-Create Missing' or 'Create Specific' mode."))
            # Return existing gamedays - ALL matches will be distributed across them
            round_records = [existing_rounds[seq] for seq in available_rounds]
            # Bypass the normal round creation - just return gamedays
            return round_records
        elif round_mode == "explicit":
            # Create exactly requested_rounds; must be at least the minimum needed
            if requested_rounds < len(rounds):
                raise UserError(_(
                    "Requested %(requested)d round(s) is fewer than the minimum %(needed)d "
                    "required for %(count)d participants. Please request at least %(needed)d rounds."
                ) % {"requested": requested_rounds, "needed": len(rounds), "count": len(rounds) + 1})
            target_rounds = requested_rounds
        else:
            # Auto mode: create as many as needed (original behavior)
            target_rounds = len(rounds)

        round_records = []
        for round_number in range(1, target_rounds + 1):
            round_vals = {
                "name": _("Round %(number)s") % {"number": round_number},
            }
            if schedule_by_round and start_dt:
                round_vals["round_date"] = (
                    fields.Datetime.to_datetime(start_dt)
                    + timedelta(hours=(round_number - 1) * round_interval_hours)
                ).date()
            if venue_rec and "venue_id" in Round._fields:
                round_vals["venue_id"] = venue_rec.id

            round_record = existing_rounds.get(round_number)
            if round_record:
                # Update existing round with new values if empty
                write_vals = {}
                if not round_record.name and round_vals.get("name"):
                    write_vals["name"] = round_vals["name"]
                for field_name in ("round_date", "venue_id"):
                    if field_name in round_vals and field_name in round_record._fields and not round_record[field_name]:
                        write_vals[field_name] = round_vals[field_name]
                if write_vals:
                    round_record.write(write_vals)
                round_records.append(round_record)
            else:
                # Create new round
                create_vals = {
                    "stage_id": stage.id,
                    "group_id": group.id if group else False,
                    "sequence": round_number,
                    "name": round_vals.get("name", _("Round %(number)s") % {"number": round_number}),
                }
                if schedule_by_round and start_dt:
                    create_vals["round_date"] = round_vals["round_date"]
                if venue_rec and "venue_id" in Round._fields:
                    create_vals["venue_id"] = venue_rec.id
                round_records.append(Round.create(create_vals))
        return round_records

    def _get_round_base_datetime(
        self,
        round_record,
        start_dt,
        round_number,
        schedule_by_round,
        round_interval_hours,
    ):
        """Return round base datetime."""
        if not start_dt:
            return False

        start_dt = fields.Datetime.to_datetime(start_dt)
        if round_record.round_date:
            return datetime.combine(round_record.round_date, start_dt.time())
        if schedule_by_round:
            return start_dt + timedelta(hours=(round_number - 1) * round_interval_hours)
        return False

    def _create_matches(self, tournament, stage, rounds, options):
        """
        Create `federation.match` records from rounds (list of rounds -> list of pairs).

        Scheduling behavior depends on options:
        - If `schedule_by_round` is True and `start_datetime` is set, each round is
          scheduled at `start_datetime + round_index * round_interval_hours` and
          intra-round spacing uses `interval_hours`.
        - Otherwise matches are scheduled sequentially across all rounds using
          `interval_hours` between matches.
        """
        Match = self.env["federation.match"]
        start_dt = options.get("start_datetime")
        interval = options.get("interval_hours", 0)
        round_interval = options.get("round_interval_hours")
        venue = options.get("venue", "")
        group = options.get("group")
        schedule_by_round = bool(options.get("schedule_by_round"))
        round_mode = options.get("round_mode", "auto")

        created = []

        # Try to resolve a venue record if a venue name was provided
        Venue = self.env.get("federation.venue")
        venue_rec = None
        if venue and Venue is not None:
            venue_rec = Venue.search([("name", "=", venue)], limit=1)

        if not round_interval:
            round_interval = interval or 24

        round_records = self._get_round_records(
            stage,
            rounds,
            group=group,
            start_dt=start_dt,
            schedule_by_round=schedule_by_round,
            round_interval_hours=round_interval,
            venue_rec=venue_rec,
            round_mode=options.get("round_mode", "auto"),
            requested_rounds=options.get("requested_rounds", 0),
        )

        sequential_index = 0

        # If we have fewer round records than round sets, cycle through them
        if len(round_records) < len(rounds) and round_mode == "existing":
            _logger.info(
                "Spreading %d match sets across %d existing rounds",
                len(rounds), len(round_records)
            )

        for round_number, round_pairs in enumerate(rounds, start=1):
            # Cycle through round records if needed (for "existing" mode)
            round_record = round_records[(round_number - 1) % len(round_records)]
            ordered_entries = self._get_ordered_round_entries(round_pairs)
            round_base = self._get_round_base_datetime(
                round_record,
                start_dt,
                round_number,
                schedule_by_round,
                round_interval,
            )

            for match_index, entry in enumerate(ordered_entries):
                vals = {
                    "tournament_id": tournament.id,
                    "stage_id": stage.id,
                    "home_team_id": entry["home"].id,
                    "away_team_id": entry["away"].id,
                    "round_id": round_record.id,
                    "round_number": round_record.sequence if round_record.sequence else round_number,
                    "state": "draft",
                }
                if group:
                    vals["group_id"] = group.id

                if venue_rec and Venue is not None:
                    vals["venue_id"] = round_record.venue_id.id if "venue_id" in round_record._fields and round_record.venue_id else venue_rec.id

                if round_base:
                    if interval:
                        vals["date_scheduled"] = round_base + timedelta(hours=match_index * interval)
                    else:
                        vals["date_scheduled"] = round_base
                elif start_dt and interval:
                    vals["date_scheduled"] = fields.Datetime.to_datetime(start_dt) + timedelta(hours=sequential_index * interval)
                elif start_dt:
                    vals["date_scheduled"] = start_dt

                created.append(Match.create(vals))
                sequential_index += 1

        return created