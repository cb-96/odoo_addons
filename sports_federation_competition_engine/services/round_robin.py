import logging
from datetime import datetime, timedelta

from odoo import fields, models, _
from odoo.exceptions import UserError  # noqa: F401 — kept for import compatibility

from odoo.addons.sports_federation_tournament.workflow_states import MATCH_STATE_DRAFT

_logger = logging.getLogger(__name__)


class RoundRobinService(models.AbstractModel):
    _name = "federation.round.robin.service"
    _inherit = "federation.base.schedule.service"
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
        for _r in range(repeats):
            rounds.extend(base_rounds)

        matches = self._create_matches(tournament, stage, rounds, options)

        _logger.info(
            "Generated %d round-robin matches for tournament %s, stage %s",
            len(matches),
            tournament.name,
            stage.name,
        )
        return matches

    def _validate_inputs(self, tournament, stage, participants, options):
        """Validate inputs."""
        self._validate_tournament_state(tournament)
        self._validate_participant_count(participants)

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
        mixed = [
            entry for entry in entries if entry["gender"] not in ("male", "female")
        ]

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

    def _get_round_records(self, stage, group=False):
        """Return pre-defined gameday records for the stage, ordered by sequence.

        Matches are distributed across these gamedays by cycling when there are
        more algorithm rounds than available gamedays.

        Raises:
            UserError: if no gamedays exist for the stage/group.
        """
        existing = self._get_stage_rounds(stage, group=group)
        if not existing:
            raise UserError(
                _(
                    "No gamedays defined for this stage. "
                    "Create at least one gameday before generating matches."
                )
            )
        return list(existing)

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
        created = []

        # Try to resolve a venue record if a venue name was provided
        Venue = self.env.get("federation.venue")
        venue_rec = None
        if venue and Venue is not None:
            venue_rec = Venue.search([("name", "=", venue)], limit=1)

        if not round_interval:
            round_interval = interval or 24

        round_records = self._get_round_records(stage, group=group)

        sequential_index = 0

        if len(round_records) < len(rounds):
            _logger.info(
                "Spreading %d algorithm rounds across %d gamedays",
                len(rounds),
                len(round_records),
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
                    "round_number": (
                        round_record.sequence if round_record.sequence else round_number
                    ),
                    "state": MATCH_STATE_DRAFT,
                }
                if group:
                    vals["group_id"] = group.id

                if venue_rec and Venue is not None:
                    vals["venue_id"] = (
                        round_record.venue_id.id
                        if "venue_id" in round_record._fields and round_record.venue_id
                        else venue_rec.id
                    )

                if round_base:
                    if interval:
                        vals["date_scheduled"] = round_base + timedelta(
                            hours=match_index * interval
                        )
                    else:
                        vals["date_scheduled"] = round_base
                elif start_dt and interval:
                    vals["date_scheduled"] = fields.Datetime.to_datetime(
                        start_dt
                    ) + timedelta(hours=sequential_index * interval)
                elif start_dt:
                    vals["date_scheduled"] = start_dt

                created.append(Match.create(vals))
                sequential_index += 1

        return created
