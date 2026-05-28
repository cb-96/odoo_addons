from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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

    _unique_tournament_stage_group_name = models.Constraint(
        "UNIQUE(tournament_id, stage_id, group_id, name)",
        "A standing with this name already exists for this tournament/stage/group.",
    )

    @api.depends("line_ids")
    def _compute_line_count(self):
        """Compute line count."""
        for record in self:
            record.line_count = len(record.line_ids)

    def action_view_lines(self):
        """Execute the view lines action."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "sports_federation_standings.action_federation_standing_line"
        )
        action["domain"] = [("standing_id", "=", self.id)]
        action["context"] = {"default_standing_id": self.id}
        return action

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
        """Get points values for win/draw/loss."""
        self.ensure_one()
        rule_set = self._get_rule_set()
        if rule_set:
            return {
                "win": rule_set.points_win or 3,
                "draw": rule_set.points_draw or 1,
                "loss": rule_set.points_loss or 0,
            }
        # Default fallback
        return {"win": 3, "draw": 1, "loss": 0}

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

    def _sort_standings(self, stats):
        """Sort standings according to the specified order.

        Order:
        1. points desc
        2. wins desc
        3. score_for - score_against desc
        4. score_for desc
        5. team display name asc
        """
        participants = self._get_participants()
        participant_map = {p.id: p for p in participants}

        # Build list of (participant_id, stats) tuples for sorting
        items = list(stats.items())

        def sort_key(item):
            """Handle sort key."""
            pid, s = item
            participant = participant_map.get(pid)
            team_name = participant.team_id.name if participant else ""
            return (
                -s["points"],
                -s["won"],
                -(s["score_for"] - s["score_against"]),
                -s["score_for"],
                team_name,
            )

        items.sort(key=sort_key)
        return items

    def _compute_tiebreak_notes(self, sorted_items, participant_map):
        """Return {pid: tiebreak_notes_str} explaining rank vs the item above.

        For each item that shares the same point total as the item ranked
        immediately above it, the note records which criterion separated them.
        Items ranked by points alone (no tie) receive an empty string.
        """
        notes = {}
        for i, (pid, s) in enumerate(sorted_items):
            if i == 0:
                notes[pid] = ""
                continue
            prev_pid, prev_s = sorted_items[i - 1]
            if prev_s["points"] != s["points"]:
                notes[pid] = ""
            elif prev_s["won"] != s["won"]:
                notes[pid] = _("Ranked by wins")
            elif (prev_s["score_for"] - prev_s["score_against"]) != (
                s["score_for"] - s["score_against"]
            ):
                notes[pid] = _("Ranked by goal difference")
            elif prev_s["score_for"] != s["score_for"]:
                notes[pid] = _("Ranked by goals scored")
            else:
                notes[pid] = _("Ranked alphabetically by team name")
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
