from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


def _dedupe_reasons(reasons):
    """Handle dedupe reasons."""
    unique_reasons = []
    seen = set()
    for reason in reasons:
        if reason and reason not in seen:
            unique_reasons.append(reason)
            seen.add(reason)
    return unique_reasons


class FederationMatchSheet(models.Model):
    _name = "federation.match.sheet"
    _description = "Match Sheet"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(
        compute="_compute_name",
        store=True,
        readonly=False,
    )
    match_id = fields.Many2one(
        "federation.match",
        string="Match",
        required=True,
        ondelete="cascade",
        index=True,
    )
    match_kickoff = fields.Datetime(
        related="match_id.date_scheduled",
        string="Match Kickoff",
        store=True,
        index=True,
        readonly=True,
    )
    match_scheduled_date = fields.Date(
        related="match_id.scheduled_date",
        string="Match Date",
        store=True,
        index=True,
        readonly=True,
    )
    team_id = fields.Many2one(
        "federation.team",
        string="Team",
        required=True,
        ondelete="restrict",
        index=True,
    )
    # Computed helper used as domain source for team_id in the form view.
    # Returns the IDs of the home and away teams on the linked match.
    match_team_ids = fields.Many2many(
        "federation.team",
        compute="_compute_match_team_ids",
        string="Match Teams",
    )
    # Computed helper used as domain source for player_id in sheet lines.
    # When a roster is selected, only players on that roster are returned.
    roster_player_ids = fields.Many2many(
        "federation.player",
        compute="_compute_roster_player_ids",
        string="Roster Players",
    )
    roster_id = fields.Many2one(
        "federation.team.roster",
        string="Roster",
        ondelete="set null",
        index=True,
    )
    side = fields.Selection(
        [
            ("home", "Home"),
            ("away", "Away"),
            ("other", "Other"),
        ],
        required=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("approved", "Approved"),
            ("locked", "Locked"),
        ],
        default="draft",
        required=True,
    )
    line_ids = fields.One2many(
        "federation.match.sheet.line",
        "match_sheet_id",
        string="Sheet Lines",
    )
    line_count = fields.Integer(
        compute="_compute_line_count",
        string="Line Count",
    )
    ready_for_submission = fields.Boolean(
        compute="_compute_readiness",
        string="Ready For Submission",
        store=True,
    )
    readiness_feedback = fields.Text(
        compute="_compute_readiness",
        string="Readiness Feedback",
        store=True,
    )
    substitution_count = fields.Integer(
        compute="_compute_substitution_count",
        string="Substitution Count",
    )
    locked_on = fields.Datetime(string="Locked On", readonly=True)
    locked_by_id = fields.Many2one(
        "res.users",
        string="Locked By",
        readonly=True,
    )
    audit_event_ids = fields.One2many(
        "federation.participation.audit",
        "match_sheet_id",
        string="Audit Events",
    )
    gameday_roster_limit = fields.Integer(
        compute="_compute_participation",
        compute_sudo=True,
        string="Max Players on Gameday Roster",
    )
    match_participant_limit = fields.Integer(
        compute="_compute_participation",
        compute_sudo=True,
        string="Max Players per Match",
    )
    participant_count = fields.Integer(
        compute="_compute_participation",
        compute_sudo=True,
        string="Playing This Match",
    )
    crossed_out_count = fields.Integer(
        compute="_compute_participation",
        compute_sudo=True,
        string="Crossed Out",
    )
    participation_feedback = fields.Char(
        compute="_compute_participation",
        compute_sudo=True,
        string="Match Participation",
    )
    can_record_participation = fields.Boolean(
        compute="_compute_participation",
        compute_sudo=True,
        string="Can Cross Out Players",
    )
    coach_name = fields.Char(string="Coach Name")
    manager_name = fields.Char(string="Manager Name")
    notes = fields.Text(string="Notes")

    _unique_match_team_side = models.Constraint(
        "UNIQUE(match_id, team_id, side)",
        "A match sheet already exists for this team and side in this match.",
    )

    @api.depends("line_ids")
    def _compute_line_count(self):
        """Compute line count."""
        for record in self:
            record.line_count = len(record.line_ids)

    @api.depends("match_id", "team_id")
    def _compute_name(self):
        for rec in self:
            if rec.match_id and rec.team_id:
                rec.name = f"{rec.match_id.display_name} – {rec.team_id.display_name}"
            elif rec.match_id:
                rec.name = rec.match_id.display_name
            elif rec.team_id:
                rec.name = rec.team_id.display_name
            elif not rec.name:
                rec.name = _("New Match Sheet")

    @api.depends("match_id", "match_id.home_team_id", "match_id.away_team_id")
    def _compute_match_team_ids(self):
        """Return the home and away teams of the linked match for domain filtering."""
        for record in self:
            if record.match_id:
                teams = record.match_id.home_team_id | record.match_id.away_team_id
                record.match_team_ids = teams
            else:
                record.match_team_ids = self.env["federation.team"]

    @api.depends("roster_id", "roster_id.line_ids", "roster_id.line_ids.player_id")
    def _compute_roster_player_ids(self):
        for rec in self:
            if rec.roster_id:
                rec.roster_player_ids = rec.roster_id.line_ids.mapped("player_id")
            else:
                rec.roster_player_ids = self.env["federation.player"]

    @api.onchange("match_id")
    def _onchange_match_id(self):
        """Clear team/roster when the match changes and auto-derive side when possible."""
        if not self.match_id:
            self.team_id = False
            self.roster_id = False
            return

        match = self.match_id
        # Clear team if it is no longer part of the new match
        if self.team_id and self.team_id not in (
            match.home_team_id | match.away_team_id
        ):
            self.team_id = False
            self.roster_id = False

    @api.onchange("team_id")
    def _onchange_team_id(self):
        """Clear roster when team changes and auto-set the side field."""
        if not self.team_id:
            self.roster_id = False
            return

        # Clear roster if it belongs to a different team
        if self.roster_id and self.roster_id.team_id != self.team_id:
            self.roster_id = False

        # Auto-set side when the team unambiguously maps to one side
        if self.match_id:
            match = self.match_id
            if (
                self.team_id == match.home_team_id
                and self.team_id != match.away_team_id
            ):
                self.side = "home"
            elif (
                self.team_id == match.away_team_id
                and self.team_id != match.home_team_id
            ):
                self.side = "away"

    @api.depends("line_ids.entered_minute")
    def _compute_substitution_count(self):
        """Compute substitution count."""
        for record in self:
            record.substitution_count = len(
                record.line_ids.filtered(lambda line: bool(line.entered_minute))
            )

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        records = super().create(vals_list)
        for record in records:
            record._log_audit_event(
                "match_sheet_created",
                _("Match sheet '%(sheet)s' created for match '%(match)s'.")
                % {
                    "sheet": record.display_name,
                    "match": record.match_id.display_name,
                },
            )
            record._inherit_existing_gameday_lineup()
        return records

    def write(self, vals):
        """Update records with module-specific side effects."""
        if not self.env.context.get("bypass_match_sheet_lock"):
            locked_records = self.filtered(lambda rec: rec.state == "locked")
            if locked_records:
                raise ValidationError(_("Locked match sheets cannot be modified."))
            approved_records = self.filtered(lambda rec: rec.state == "approved")
            allowed_on_approved = {"state", "notes", "locked_on", "locked_by_id"}
            if approved_records and any(
                field not in allowed_on_approved for field in vals
            ):
                raise ValidationError(
                    _(
                        "Approved match sheets cannot change their declared squad. Record substitutions on the sheet lines instead."
                    )
                )
        return super().write(vals)

    @api.depends(
        "roster_id",
        "roster_id.status",
        "roster_id.readiness_feedback",
        "line_ids",
        "line_ids.player_id",
        "line_ids.roster_line_id",
        "line_ids.eligible",
        "line_ids.eligibility_feedback",
        "match_id",
        "match_id.date_scheduled",
    )
    def _compute_readiness(self):
        """Compute readiness."""
        for record in self:
            issues = record._get_submission_issues()
            record.ready_for_submission = not bool(issues)
            record.readiness_feedback = "\n".join(issues) if issues else False

    @api.depends(
        "state",
        "roster_id",
        "line_ids",
        "line_ids.crossed_out",
        "match_id.state",
        "match_id.tournament_id",
    )
    def _compute_participation(self):
        """Summarize this match's participants from the shared gameday roster."""
        for record in self:
            playing = record.line_ids.filtered(lambda line: not line.crossed_out)
            record.gameday_roster_limit = record._get_gameday_roster_limit()
            record.match_participant_limit = record._get_match_participant_limit()
            record.participant_count = len(playing)
            record.crossed_out_count = len(record.line_ids) - len(playing)
            record.participation_feedback = (
                "\n".join(record._get_participation_issues()) or False
            )
            record.can_record_participation = record._participation_is_open()

    @api.constrains("side", "team_id", "match_id")
    def _check_side_team_consistency(self):
        """Validate side team consistency."""
        for record in self:
            if record.side == "home" and record.match_id.home_team_id:
                if record.team_id != record.match_id.home_team_id:
                    raise ValidationError(
                        _("Home side team must match the match home team.")
                    )
            elif record.side == "away" and record.match_id.away_team_id:
                if record.team_id != record.match_id.away_team_id:
                    raise ValidationError(
                        _("Away side team must match the match away team.")
                    )

    def _get_effective_rule_set(self):
        """Return effective rule set."""
        self.ensure_one()
        if self.roster_id:
            return self.roster_id._get_effective_rule_set()
        service = self.env.get("federation.eligibility.service")
        if service is not None:
            return service._resolve_rule_set(self.match_id)
        return self.env["federation.rule.set"]

    def _get_reference_date(self):
        """Return reference date."""
        self.ensure_one()
        if self.match_id.date_scheduled:
            return fields.Datetime.to_datetime(self.match_id.date_scheduled).date()
        return fields.Date.context_today(self)

    def _get_gameday_roster_limit(self):
        """Players allowed on the team's shared roster for one gameday."""
        self.ensure_one()
        rule_set = self._get_effective_rule_set()
        if rule_set and rule_set.gameday_roster_max_size:
            return rule_set.gameday_roster_max_size
        if self.roster_id:
            return self.roster_id._get_required_player_bounds()[1]
        return rule_set.squad_max_size if rule_set else 0

    def _get_match_participant_limit(self):
        """Players allowed to take part in this one match (0 = no extra limit)."""
        self.ensure_one()
        rule_set = self._get_effective_rule_set()
        return rule_set.match_player_max_size if rule_set else 0

    def _participation_is_open(self):
        """Players can be crossed out until the match is finished."""
        self.ensure_one()
        return (
            self.state in ("submitted", "approved")
            and bool(self.line_ids)
            and self.match_id.state not in ("done", "cancelled")
        )

    def _get_participation_issues(self):
        """Return what still blocks this match's participant list."""
        self.ensure_one()
        limit = self._get_match_participant_limit()
        playing = len(self.line_ids.filtered(lambda line: not line.crossed_out))
        if limit and playing > limit:
            return [
                _(
                    "%(playing)s players are listed for this match; at most "
                    "%(limit)s may play. Cross out %(extra)s player(s)."
                )
                % {"playing": playing, "limit": limit, "extra": playing - limit}
            ]
        return []

    def _get_submission_issues(self):
        """Return submission issues."""
        self.ensure_one()
        issues = []

        if not self.roster_id:
            issues.append(
                _("Select an active roster before submitting the match sheet.")
            )
        elif self.roster_id.status != "active":
            issues.append(_("The selected roster must be active before submission."))

        if not self.line_ids:
            issues.append(_("Add at least one match-sheet line before submission."))

        eligible_line_count = 0
        for line in self.line_ids:
            reasons = line._get_eligibility_reasons()
            if reasons:
                issues.append(
                    _("Player '%(player)s': %(reasons)s")
                    % {
                        "player": line.player_id.display_name,
                        "reasons": "; ".join(reasons),
                    }
                )
            else:
                eligible_line_count += 1

        if self.roster_id:
            min_required = self.roster_id._get_required_player_bounds()[0]
        else:
            rule_set = self._get_effective_rule_set()
            min_required = rule_set.squad_min_size if rule_set else 0
        max_allowed = self._get_gameday_roster_limit()

        if min_required and eligible_line_count < min_required:
            issues.append(
                _(
                    "Eligible submitted players (%(actual)s) are below the required minimum of %(expected)s."
                )
                % {"actual": eligible_line_count, "expected": min_required}
            )
        if max_allowed and len(self.line_ids) > max_allowed:
            issues.append(
                _(
                    "The gameday roster lists %(actual)s players; the maximum is %(expected)s."
                )
                % {"actual": len(self.line_ids), "expected": max_allowed}
            )

        return issues

    def _requires_gameday_lineup_approval(self):
        """Return whether this declaration needs a separate approval handoff."""
        self.ensure_one()
        edition = self.match_id.tournament_id.edition_id
        if not edition or "match_sheet_approval_required" not in edition._fields:
            # Legacy tournaments keep their established explicit approval flow.
            return True
        return bool(edition.match_sheet_approval_required)

    def _log_audit_event(self, event_type, description, player=False):
        """Handle log audit event."""
        Audit = self.env.get("federation.participation.audit")
        if Audit is None:
            return False
        for record in self:
            Audit.create_event(
                event_type=event_type,
                description=description,
                team=record.team_id,
                roster=record.roster_id,
                match_sheet=record,
                match=record.match_id,
                player=player,
            )
        return True

    def action_submit(self):
        """Execute the submit action."""
        for source, _initial_sheets in self._get_action_gameday_groups():
            sheets = source._synchronize_gameday_lineup(source)
            for record in sheets.filtered(lambda sheet: sheet.state == "draft"):
                issues = record._get_submission_issues()
                if issues:
                    raise ValidationError(
                        _(
                            "Match sheet '%(sheet)s' is not ready for submission:\n"
                            "- %(issues)s"
                        )
                        % {
                            "sheet": record.display_name,
                            "issues": "\n- ".join(issues),
                        }
                    )
            submitted = sheets.filtered(lambda sheet: sheet.state == "draft")
            submitted.write({"state": "submitted"})
            for record in submitted:
                record._log_audit_event(
                    "match_sheet_submitted",
                    _("Match sheet '%(sheet)s' submitted with its game-day lineup.")
                    % {"sheet": record.display_name},
                )
            if submitted and not source._requires_gameday_lineup_approval():
                # Streamlined mode still uses the existing approval command so
                # readiness checks, synchronization and audit events are kept.
                source.action_approve()

    def action_reset_to_draft(self):
        """Reset a submitted match sheet back to draft for corrections."""
        for record in self:
            if record.state != "submitted":
                raise ValidationError(
                    _("Only submitted match sheets can be reset to draft.")
                )
        reset_sheets = self.env["federation.match.sheet"]
        for _source, sheets in self._get_action_gameday_groups():
            reset_sheets |= sheets.filtered(lambda sheet: sheet.state == "submitted")
        reset_sheets.write({"state": "draft"})
        for record in reset_sheets:
            record._log_audit_event(
                "match_sheet_reset",
                _("Match sheet '%(sheet)s' reset with its game-day lineup.")
                % {"sheet": record.display_name},
            )

    def action_approve(self):
        """Execute the approve action."""
        for record in self:
            if record.state != "submitted":
                raise ValidationError(_("Only submitted match sheets can be approved."))
        for source, _initial_sheets in self._get_action_gameday_groups():
            sheets = source._synchronize_gameday_lineup(source)
            mutable_sheets = sheets.filtered(
                lambda sheet: sheet.state in ("draft", "submitted")
            )
            for record in mutable_sheets:
                issues = record._get_submission_issues()
                if issues:
                    raise ValidationError(
                        _(
                            "Match sheet '%(sheet)s' is not ready for approval:\n"
                            "- %(issues)s"
                        )
                        % {
                            "sheet": record.display_name,
                            "issues": "\n- ".join(issues),
                        }
                    )
            newly_submitted = mutable_sheets.filtered(
                lambda sheet: sheet.state == "draft"
            )
            if newly_submitted:
                newly_submitted.write({"state": "submitted"})
                for record in newly_submitted:
                    record._log_audit_event(
                        "match_sheet_submitted",
                        _(
                            "Match sheet '%(sheet)s' submitted through game-day "
                            "lineup approval."
                        )
                        % {"sheet": record.display_name},
                    )
            mutable_sheets.write({"state": "approved"})
            for record in mutable_sheets:
                record._log_audit_event(
                    "match_sheet_approved",
                    _("Match sheet '%(sheet)s' game-day lineup approved.")
                    % {"sheet": record.display_name},
                )

    def action_lock(self):
        """Execute the lock action."""
        for record in self:
            if record.state != "approved":
                raise ValidationError(_("Only approved match sheets can be locked."))
            issues = record._get_participation_issues()
            if issues:
                raise ValidationError(
                    _("Match sheet '%(sheet)s' cannot be locked: %(issues)s")
                    % {"sheet": record.display_name, "issues": " ".join(issues)}
                )
        self.write(
            {
                "state": "locked",
                "locked_on": fields.Datetime.now(),
                "locked_by_id": self.env.user.id,
            }
        )
        for record in self:
            record._log_audit_event(
                "match_sheet_locked",
                _("Match sheet '%(sheet)s' locked.") % {"sheet": record.display_name},
            )

    def action_sync_gameday_roster(self):
        """Share this draft gameday roster with the team's other matches that day."""
        for record in self:
            if record.state != "draft":
                raise ValidationError(
                    _("Only a draft gameday roster can be shared again.")
                )
            record._synchronize_gameday_lineup(record)
        return True

    def action_set_crossed_out(self, player_ids):
        """Record which gameday players do not play this match.

        ``player_ids`` is the complete crossed-out list for this match. Other
        matches on the same gameday keep their own list.
        """
        self.ensure_one()
        if not self._participation_is_open():
            raise ValidationError(
                _(
                    "Players can be crossed out once the gameday roster is "
                    "submitted, until the match is finished."
                )
            )
        try:
            requested = {int(player_id) for player_id in (player_ids or [])}
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                _("Select players from this gameday roster.")
            ) from exc
        listed = set(self.line_ids.mapped("player_id").ids)
        if requested - listed:
            raise ValidationError(_("Select players from this gameday roster."))
        limit = self._get_match_participant_limit()
        playing = len(listed - requested)
        if limit and playing > limit:
            raise ValidationError(
                _(
                    "%(playing)s players would play; at most %(limit)s may play. "
                    "Cross out %(extra)s more player(s)."
                )
                % {"playing": playing, "limit": limit, "extra": playing - limit}
            )
        if not playing:
            raise ValidationError(_("At least one player must play this match."))
        ineligible = []
        for line in self.line_ids.filtered(
            lambda item: item.player_id.id not in requested
        ):
            reasons = line._get_eligibility_reasons()
            if reasons:
                ineligible.append(
                    "%s (%s)" % (line.player_id.display_name, "; ".join(reasons))
                )
        if ineligible:
            raise ValidationError(
                _(
                    "These players are no longer eligible and must be crossed "
                    "out for this match: %(players)s"
                )
                % {"players": ", ".join(ineligible)}
            )
        for line in self.line_ids:
            crossed = line.player_id.id in requested
            if line.crossed_out != crossed:
                line.write({"crossed_out": crossed})
        return True
