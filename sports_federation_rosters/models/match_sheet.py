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

    def _get_gameday_scope(self):
        """Return the explicit match-day scope, or a tournament/date fallback."""
        self.ensure_one()
        match = self.match_id
        publication = (
            match.schedule_publication_id
            if "schedule_publication_id" in match._fields
            else False
        )
        matchday = (
            publication.matchday_id
            if publication and "matchday_id" in publication._fields
            else False
        )
        if matchday:
            return ("matchday", matchday.id)
        if self.match_scheduled_date and match.tournament_id:
            return (
                "tournament_date",
                match.tournament_id.id,
                self.match_scheduled_date,
            )
        return False

    def _get_gameday_sheets(self):
        """Return all sheets sharing this team's game-day declaration scope."""
        self.ensure_one()
        scope = self._get_gameday_scope()
        if not scope:
            return self
        domain = [
            ("team_id", "=", self.team_id.id),
            ("match_id.state", "!=", "cancelled"),
        ]
        if scope[0] == "matchday":
            domain.append(
                ("match_id.schedule_publication_id.matchday_id", "=", scope[1])
            )
        else:
            domain.extend(
                [
                    ("match_id.tournament_id", "=", scope[1]),
                    ("match_scheduled_date", "=", scope[2]),
                ]
            )
        return self.search(domain, order="match_kickoff asc, id asc")

    def _declared_lineup_signature(self):
        """Return the match-independent portion of a game-day lineup."""
        self.ensure_one()
        lines = sorted(
            (
                line.player_id.id,
                line.roster_line_id.id or False,
                bool(line.is_starter),
                bool(line.is_substitute),
                bool(line.is_captain),
                line.jersey_number or "",
            )
            for line in self.line_ids
        )
        return (self.roster_id.id or False, tuple(lines))

    def _get_existing_gameday_lineup_source(self):
        """Choose an existing declaration to initialize a newly-created sheet."""
        self.ensure_one()
        candidates = (self._get_gameday_sheets() - self).filtered("line_ids")
        if not candidates:
            return self.env["federation.match.sheet"]
        state_rank = {"locked": 4, "approved": 3, "submitted": 2, "draft": 1}
        return candidates.sorted(
            key=lambda sheet: (-state_rank.get(sheet.state, 0), sheet.id)
        )[:1]

    def _copy_declared_lineup_from(self, source, inherit_approval=False):
        """Copy only declaration fields; substitutions remain match-specific."""
        self.ensure_one()
        source.ensure_one()
        if self == source:
            return False
        if self.state in ("approved", "locked"):
            if self._declared_lineup_signature() != source._declared_lineup_signature():
                raise ValidationError(
                    _(
                        "Game-day match sheets for team '%(team)s' must use the "
                        "same approved lineup."
                    )
                    % {"team": self.team_id.display_name}
                )
            return False

        target_vals = {"roster_id": source.roster_id.id or False}
        if source.coach_name and not self.coach_name:
            target_vals["coach_name"] = source.coach_name
        if source.manager_name and not self.manager_name:
            target_vals["manager_name"] = source.manager_name
        self.write(target_vals)
        self.line_ids.unlink()
        line_values = [
            {
                "match_sheet_id": self.id,
                "player_id": line.player_id.id,
                "roster_line_id": line.roster_line_id.id or False,
                "is_starter": line.is_starter,
                "is_substitute": line.is_substitute,
                "is_captain": line.is_captain,
                "jersey_number": line.jersey_number,
            }
            for line in source.line_ids
        ]
        if line_values:
            self.env["federation.match.sheet.line"].create(line_values)
        if inherit_approval and source.state in ("approved", "locked"):
            self.write({"state": "approved"})
            self._log_audit_event(
                "match_sheet_approved",
                _(
                    "Match sheet '%(sheet)s' inherited the approved game-day lineup."
                )
                % {"sheet": self.display_name},
            )
        elif inherit_approval and source.state == "submitted":
            self.write({"state": "submitted"})
        return True

    def _inherit_existing_gameday_lineup(self):
        """Initialize new sheets from a previously declared lineup for the day."""
        for record in self.filtered(lambda sheet: sheet.state == "draft"):
            source = record._get_existing_gameday_lineup_source()
            if source:
                record._copy_declared_lineup_from(source, inherit_approval=True)

    def _synchronize_gameday_lineup(self, source):
        """Apply one declaration to every mutable sheet in the game-day scope."""
        source.ensure_one()
        sheets = source._get_gameday_sheets()
        for sheet in sheets - source:
            sheet._copy_declared_lineup_from(source)
        return sheets

    def _get_action_gameday_groups(self):
        """Yield one selected source and complete sheet set per game-day scope."""
        seen = set()
        for record in self:
            scope = (
                record.team_id.id,
                record._get_gameday_scope() or ("sheet", record.id),
            )
            if scope in seen:
                continue
            seen.add(scope)
            yield record, record._get_gameday_sheets()

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
            min_required, max_allowed = self.roster_id._get_required_player_bounds()
        else:
            rule_set = self._get_effective_rule_set()
            min_required = rule_set.squad_min_size if rule_set else 0
            max_allowed = rule_set.squad_max_size if rule_set else 0

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
                    "Submitted players (%(actual)s) exceed the allowed maximum of %(expected)s."
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
