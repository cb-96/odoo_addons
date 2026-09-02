import logging
from uuid import uuid4

from odoo.addons.sports_federation_base.correlation import ensure_correlation_id
from odoo import api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class FederationStanding(models.Model):
    _name = "federation.standing"
    _description = "Federation Standing"
    _inherit = ["mail.thread"]
    _order = "tournament_id, stage_id, group_id, name"

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    tournament_id = fields.Many2one(
        "federation.tournament",
        string="Tournament",
        required=True,
        ondelete="cascade",
        index=True,
    )
    stage_id = fields.Many2one(
        "federation.tournament.stage",
        string="Stage",
        ondelete="cascade",
        index=True,
    )
    group_id = fields.Many2one(
        "federation.tournament.group",
        string="Group",
        ondelete="cascade",
        index=True,
    )
    competition_id = fields.Many2one(
        "federation.competition",
        string="Competition",
        ondelete="cascade",
        index=True,
    )
    rule_set_id = fields.Many2one(
        "federation.rule.set",
        string="Rule Set",
        ondelete="set null",
        index=True,
        help="Rule set used to calculate points (win/draw/loss values) and tie-break"
        " order for this standing. When left empty, the rule set is inherited in"
        " order from: stage → tournament → competition. Set explicitly here only"
        " when this standing needs different scoring rules than its parent objects.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("computed", "Computed"),
            ("frozen", "Frozen"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    line_ids = fields.One2many(
        "federation.standing.line",
        "standing_id",
        string="Lines",
    )
    line_count = fields.Integer(
        compute="_compute_line_count",
        string="Line Count",
    )
    computed_on = fields.Datetime(
        string="Computed On",
        readonly=True,
    )
    notes = fields.Text(string="Notes")
    recompute_job_ids = fields.One2many(
        "federation.standing.recompute.job",
        "standing_id",
        string="Recompute Jobs",
    )
    recompute_pending_count = fields.Integer(
        compute="_compute_recompute_queue_counts",
        string="Pending Recomputes",
    )
    recompute_failed_count = fields.Integer(
        compute="_compute_recompute_queue_counts",
        string="Failed Recomputes",
    )

    _unique_tournament_stage_group_name = models.Constraint(
        "UNIQUE(tournament_id, stage_id, group_id, name)",
        "A standing with this name already exists for this tournament/stage/group.",
    )

    @api.depends("line_ids")
    def _compute_line_count(self):
        """Compute line count."""
        for record in self:
            record.line_count = len(record.line_ids)

    @api.depends("recompute_job_ids.state")
    def _compute_recompute_queue_counts(self):
        """Compute pending and failed recompute queue counters."""
        for record in self:
            record.recompute_pending_count = len(
                record.recompute_job_ids.filtered(
                    lambda job: job.state in ("pending", "running")
                )
            )
            record.recompute_failed_count = len(
                record.recompute_job_ids.filtered(lambda job: job.state == "failed")
            )

    def action_view_lines(self):
        """Execute the view lines action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_standings.action_federation_standing_line"
        )
        action["domain"] = [("standing_id", "=", self.id)]
        action["context"] = {"default_standing_id": self.id}
        return action

    def action_view_recompute_jobs(self):
        """Open queue jobs for this standing."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_standings.action_federation_standing_recompute_job"
        )
        action["domain"] = [("standing_id", "=", self.id)]
        action["context"] = {
            "default_standing_id": self.id,
            "search_default_pending": 1,
        }
        return action

    def action_queue_recompute(self):
        """Queue a recompute job for asynchronous execution."""
        self.ensure_one()
        correlation_id = ensure_correlation_id(self.env)
        key = "standing:%s:%s" % (self.id, uuid4().hex)
        queue_result = self.env["federation.standing.recompute.job"].request_recompute(
            self,
            idempotency_key=key,
            correlation_id=correlation_id,
        )
        if queue_result.get("replayed"):
            _logger.info(
                "Standing recompute replayed for standing=%s correlation_id=%s idempotency_key=%s",
                self.id,
                correlation_id,
                key,
            )
        else:
            _logger.info(
                "Standing recompute queued for standing=%s correlation_id=%s idempotency_key=%s",
                self.id,
                correlation_id,
                key,
            )
        return self.action_view_recompute_jobs()

    @api.constrains("group_id", "stage_id")
    def _check_group_stage_consistency(self):
        """Validate group stage consistency."""
        for record in self:
            if record.group_id and not record.stage_id:
                raise ValidationError("Group cannot be set without a Stage.")
            if record.group_id and record.stage_id:
                if record.group_id.stage_id != record.stage_id:
                    raise ValidationError("Group must belong to the selected Stage.")

    @api.constrains("stage_id", "tournament_id")
    def _check_stage_tournament_consistency(self):
        """Validate stage tournament consistency."""
        for record in self:
            if record.stage_id and record.tournament_id:
                if record.stage_id.tournament_id != record.tournament_id:
                    raise ValidationError(
                        "Stage must belong to the selected Tournament."
                    )

    def _get_rule_set(self):
        """Get the effective rule set for points calculation."""
        self.ensure_one()
        if self.rule_set_id:
            return self.rule_set_id
        if self.stage_id and self.stage_id.rule_set_id:
            return self.stage_id.rule_set_id
        if self.tournament_id and self.tournament_id.rule_set_id:
            return self.tournament_id.rule_set_id
        if self.competition_id and self.competition_id.rule_set_id:
            return self.competition_id.rule_set_id
        return False

    def _get_points_values(self):
        self.ensure_one()
        return self.env["federation.standings.rules"].points_map(self._get_rule_set())

    def _get_relevant_matches(self):
        """Get matches relevant for this standing computation.

        When ``sports_federation_result_control`` is installed the
        ``include_in_official_standings`` field is present on
        ``federation.match``.  Only matches explicitly approved for
        official standings are counted; contested / unapproved results
        are excluded.  When the module is absent every ``done`` match
        is counted (fallback behaviour).
        """
        self.ensure_one()
        domain = [
            ("tournament_id", "=", self.tournament_id.id),
            ("state", "=", "done"),
            ("home_team_id", "!=", False),
            ("away_team_id", "!=", False),
        ]
        if self.stage_id:
            domain.append(("stage_id", "=", self.stage_id.id))
        if self.group_id:
            domain.append(("group_id", "=", self.group_id.id))
        # If result_control is installed, only count officially approved matches
        if "include_in_official_standings" in self.env["federation.match"]._fields:
            domain.append(("include_in_official_standings", "=", True))
        return self.env["federation.match"].search(domain)

    def _get_participants(self):
        """Get participants for this standing."""
        self.ensure_one()
        domain = [
            ("tournament_id", "=", self.tournament_id.id),
        ]
        if self.stage_id:
            domain.append(("stage_id", "=", self.stage_id.id))
        if self.group_id:
            domain.append(("group_id", "=", self.group_id.id))
        return self.env["federation.tournament.participant"].search(domain)

    def _build_standing_table(self):
        """Build the standing table from matches.

        Returns a dict keyed by participant_id with stats.
        """
        self.ensure_one()
        matches = self._get_relevant_matches()
        points_values = self._get_points_values()

        # Build a dict from team_id → participant for O(1) lookup in the match loop
        participants = self._get_participants()
        participant_map = {p.team_id.id: p for p in participants}
        stats = {}
        for participant in participants:
            stats[participant.id] = {
                "played": 0,
                "won": 0,
                "drawn": 0,
                "lost": 0,
                "score_for": 0,
                "score_against": 0,
            }

        # Process matches
        for match in matches:
            # O(1) lookup instead of O(m) filtered() scan
            home_participant = participant_map.get(match.home_team_id.id)
            away_participant = participant_map.get(match.away_team_id.id)

            if not home_participant or not away_participant:
                continue

            home_pid = home_participant.id
            away_pid = away_participant.id

            # Update played count
            stats[home_pid]["played"] += 1
            stats[away_pid]["played"] += 1

            # Update scores
            stats[home_pid]["score_for"] += match.home_score
            stats[home_pid]["score_against"] += match.away_score
            stats[away_pid]["score_for"] += match.away_score
            stats[away_pid]["score_against"] += match.home_score

            # Update win/draw/loss
            if match.home_score > match.away_score:
                stats[home_pid]["won"] += 1
                stats[away_pid]["lost"] += 1
            elif match.away_score > match.home_score:
                stats[away_pid]["won"] += 1
                stats[home_pid]["lost"] += 1
            else:
                stats[home_pid]["drawn"] += 1
                stats[away_pid]["drawn"] += 1

        # Calculate points
        for pid in stats:
            stats[pid]["points"] = (
                stats[pid]["won"] * points_values["win"]
                + stats[pid]["drawn"] * points_values["draw"]
                + stats[pid]["lost"] * points_values["loss"]
            )

        return stats

    def _ranking_context(self, stats):
        participants = self._get_participants()
        participant_map = {participant.id: participant for participant in participants}
        team_to_pid = {
            participant.team_id.id: participant.id for participant in participants
        }
        matches = []
        for match in self._get_relevant_matches():
            home = team_to_pid.get(match.home_team_id.id)
            away = team_to_pid.get(match.away_team_id.id)
            if home and away:
                matches.append((home, away, match.home_score, match.away_score))
        names = {
            pid: participant.team_id.name or ""
            for pid, participant in participant_map.items()
        }
        return participant_map, matches, names

    def _rank_standings(self, stats):
        """Return ranked rows and explanations without mutating the record."""
        _participant_map, matches, names = self._ranking_context(stats)
        return self.env["federation.standings.rules"].rank(
            stats,
            rule_set=self._get_rule_set(),
            matches=matches,
            names=names,
            lot_seed=self.id,
        )

    def _sort_standings(self, stats):
        ranked, _notes = self._rank_standings(stats)
        return ranked

    def _compute_tiebreak_notes(self, sorted_items, participant_map):
        del participant_map  # Kept for compatibility with existing callers.
        _ranked, notes = self._rank_standings(dict(sorted_items))
        return notes

    def action_recompute(self):
        """Recompute the standing from matches."""
        for record in self:
            if record.state == "frozen":
                if not self.env.context.get("force_recompute"):
                    raise ValidationError(
                        "Cannot recompute a frozen standing. "
                        "Use force_recompute context to override."
                    )

            # Get sorted standings
            stats = record._build_standing_table()
            sorted_items = record._sort_standings(stats)
            participants = record._get_participants()
            participant_map = {p.id: p for p in participants}
            tiebreak_notes = record._compute_tiebreak_notes(
                sorted_items, participant_map
            )

            # Delete existing lines
            record.line_ids.unlink()

            # Create new lines with ranks
            rank = 1
            for pid, s in sorted_items:
                participant = participant_map.get(pid)
                if participant:
                    self.env["federation.standing.line"].create(
                        {
                            "standing_id": record.id,
                            "participant_id": pid,
                            "rank": rank,
                            "played": s["played"],
                            "won": s["won"],
                            "drawn": s["drawn"],
                            "lost": s["lost"],
                            "score_for": s["score_for"],
                            "score_against": s["score_against"],
                            "points": s["points"],
                            "tiebreak_notes": tiebreak_notes.get(pid, ""),
                        }
                    )
                    rank += 1

            record.write(
                {
                    "state": "computed",
                    "computed_on": fields.Datetime.now(),
                }
            )

    def action_freeze(self):
        """Freeze the standing to prevent recomputation.

        If any stage progression rules have auto_advance=True for the
        source stage/group of this standing, they are executed automatically.
        """
        for record in self:
            record.state = "frozen"
            # Trigger auto-advance progression rules
            if record.tournament_id and record.stage_id:
                Progression = self.env.get("federation.stage.progression")
                if Progression is not None:
                    domain = [
                        ("tournament_id", "=", record.tournament_id.id),
                        ("source_stage_id", "=", record.stage_id.id),
                        ("auto_advance", "=", True),
                        ("state", "=", "pending"),
                    ]
                    if record.group_id:
                        domain.append(("source_group_id", "=", record.group_id.id))
                    rules = Progression.search(domain)
                    for rule in rules:
                        rule.action_execute()
            Dispatcher = record.env.get("federation.notification.dispatcher")
            if Dispatcher is not None:
                Dispatcher.send_standing_frozen(record)

    def action_unfreeze(self):
        """Unfreeze the standing to allow recomputation."""
        for record in self:
            if record.state == "frozen":
                record.state = "computed"

    @api.model
    def cross_group_ranking(self, stage, rank_from=1, rank_to=None):
        """Rank teams across all groups in a stage at the given rank positions.

        Returns a sorted list of dicts:
            [{"team": team_record, "rank": int, "points": int,
              "score_diff": int, "score_for": int, "group": group_record}]
        """
        groups = self.env["federation.tournament.group"].search(
            [
                ("stage_id", "=", stage.id),
            ]
        )
        entries = []
        for group in groups:
            standing = self.search(
                [
                    ("tournament_id", "=", stage.tournament_id.id),
                    ("stage_id", "=", stage.id),
                    ("group_id", "=", group.id),
                    ("state", "in", ("computed", "frozen")),
                ],
                limit=1,
            )
            if not standing:
                continue
            for line in standing.line_ids:
                if line.rank < rank_from:
                    continue
                if rank_to and line.rank > rank_to:
                    continue
                entries.append(
                    {
                        "team": line.team_id,
                        "rank": line.rank,
                        "points": line.points,
                        "score_diff": line.score_diff,
                        "score_for": line.score_for,
                        "group": group,
                    }
                )

        # Sort: points desc → goal diff desc → goals for desc → team name asc
        entries.sort(
            key=lambda e: (
                -e["points"],
                -e["score_diff"],
                -e["score_for"],
                e["team"].name,
            )
        )
        return entries


class FederationStandingLine(models.Model):
    _name = "federation.standing.line"
    _description = "Federation Standing Line"
    _order = "rank, id"

    standing_id = fields.Many2one(
        "federation.standing",
        string="Standing",
        required=True,
        ondelete="cascade",
        index=True,
    )
    participant_id = fields.Many2one(
        "federation.tournament.participant",
        string="Participant",
        required=True,
        ondelete="restrict",
        index=True,
    )
    team_id = fields.Many2one(
        "federation.team",
        string="Team",
        related="participant_id.team_id",
        store=True,
    )
    club_id = fields.Many2one(
        "federation.club",
        string="Club",
        related="participant_id.club_id",
        store=True,
    )
    rank = fields.Integer(string="Rank")
    rank_badge = fields.Char(
        string="Medal",
        compute="_compute_rank_badge",
        store=True,
    )
    played = fields.Integer(string="Played", default=0)
    won = fields.Integer(string="Won", default=0)
    drawn = fields.Integer(string="Drawn", default=0)
    lost = fields.Integer(string="Lost", default=0)
    score_for = fields.Integer(string="GF", default=0)
    score_against = fields.Integer(string="GA", default=0)
    score_diff = fields.Integer(
        string="GD",
        compute="_compute_score_diff",
        store=True,
    )
    points = fields.Integer(string="Points", default=0)
    qualified = fields.Boolean(string="Qualified", default=False)
    eliminated = fields.Boolean(string="Eliminated", default=False)
    note = fields.Char(string="Note")
    tiebreak_notes = fields.Text(string="Tiebreak Notes", readonly=True)

    _unique_standing_participant = models.Constraint(
        "UNIQUE(standing_id, participant_id)",
        "A standing line already exists for this participant.",
    )

    @api.depends("score_for", "score_against")
    def _compute_score_diff(self):
        """Compute score diff."""
        for record in self:
            record.score_diff = record.score_for - record.score_against

    @api.depends("rank")
    def _compute_rank_badge(self):
        """Compute gold/silver/bronze medal emoji for top-3 positions."""
        _MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}
        for line in self:
            line.rank_badge = _MEDALS.get(line.rank, "")
