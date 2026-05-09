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


class FederationTeamRoster(models.Model):
    _name = "federation.team.roster"
    _description = "Team Roster"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char(string="Roster", tracking=True, copy=False)
    active = fields.Boolean(default=True)
    team_id = fields.Many2one(
        "federation.team",
        string="Team",
        required=True,
        ondelete="cascade",
        index=True,
        tracking=True,
    )
    season_id = fields.Many2one(
        "federation.season",
        string="Season",
        required=True,
        ondelete="restrict",
        index=True,
        tracking=True,
    )
    season_registration_id = fields.Many2one(
        "federation.season.registration",
        string="Season Registration",
        ondelete="set null",
        index=True,
    )
    competition_id = fields.Many2one(
        "federation.competition",
        string="Competition",
        ondelete="set null",
        index=True,
    )
    rule_set_id = fields.Many2one(
        "federation.rule.set",
        string="Rule Set",
        ondelete="set null",
    )
    status = fields.Selection(
        [
            ("draft", "Draft"),
            ("active", "Active"),
            ("closed", "Closed"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    valid_from = fields.Date(string="Valid From")
    valid_to = fields.Date(string="Valid To")
    line_ids = fields.One2many(
        "federation.team.roster.line",
        "roster_id",
        string="Roster Lines",
    )
    line_count = fields.Integer(
        compute="_compute_line_count",
        string="Line Count",
    )
    notes = fields.Text(string="Notes")
    club_id = fields.Many2one(
        "federation.club",
        string="Club",
        related="team_id.club_id",
        store=True,
    )
    min_players_required = fields.Integer(string="Min Players Required")
    max_players_allowed = fields.Integer(string="Max Players Allowed")
    ready_for_activation = fields.Boolean(
        compute="_compute_readiness",
        string="Ready For Activation",
        store=True,
    )
    readiness_feedback = fields.Text(
        compute="_compute_readiness",
        string="Readiness Feedback",
        store=True,
    )
    match_sheet_ids = fields.One2many(
        "federation.match.sheet",
        "roster_id",
        string="Match Sheets",
    )
    match_sheet_count = fields.Integer(
        compute="_compute_match_sheet_count",
        string="Match Sheet Count",
    )
    match_day_locked = fields.Boolean(
        compute="_compute_match_day_lock",
        string="Match-Day Locked",
    )
    match_day_lock_feedback = fields.Text(
        compute="_compute_match_day_lock",
        string="Match-Day Lock Feedback",
    )
    audit_event_ids = fields.One2many(
        "federation.participation.audit",
        "roster_id",
        string="Audit Events",
    )

    _unique_team_season_competition_name = models.Constraint(
        "UNIQUE(team_id, season_id, competition_id, name)",
        "A roster with this name already exists for this team, season, and competition.",
    )

    def _build_generated_name(self, team, season, competition=False):
        """Build generated name."""
        team_label = team.display_name if team else _("Team")
        season_label = season.display_name if season else _("Season")
        if competition:
            return _("%(team)s - %(competition)s - %(season)s Roster") % {
                "team": team_label,
                "competition": competition.display_name,
                "season": season_label,
            }
        return _("%(team)s - %(season)s Roster") % {
            "team": team_label,
            "season": season_label,
        }

    def _resolve_scope_for_name(self, vals=None, record=False):
        """Resolve scope for name."""
        vals = vals or {}
        Team = self.env["federation.team"]
        Season = self.env["federation.season"]
        Competition = self.env["federation.competition"]

        if "team_id" in vals:
            team = Team.browse(vals["team_id"]) if vals["team_id"] else Team.browse([])
        else:
            team = record.team_id if record else Team.browse([])

        if "season_id" in vals:
            season = (
                Season.browse(vals["season_id"])
                if vals["season_id"]
                else Season.browse([])
            )
        else:
            season = record.season_id if record else Season.browse([])

        if "competition_id" in vals:
            competition = (
                Competition.browse(vals["competition_id"])
                if vals["competition_id"]
                else Competition.browse([])
            )
        else:
            competition = record.competition_id if record else Competition.browse([])

        return team, season, competition

    def _get_generated_name(self, vals=None, record=False):
        """Return generated name."""
        team, season, competition = self._resolve_scope_for_name(
            vals=vals, record=record
        )
        if not team or not season:
            return False

        base_name = self._build_generated_name(team, season, competition)
        scope_domain = [
            ("team_id", "=", team.id),
            ("season_id", "=", season.id),
            ("competition_id", "=", competition.id if competition else False),
        ]
        if record and record.id:
            scope_domain.append(("id", "!=", record.id))

        name = base_name
        suffix = 2
        while self.search_count(scope_domain + [("name", "=", name)]):
            name = _("%(base)s (%(suffix)s)") % {
                "base": base_name,
                "suffix": suffix,
            }
            suffix += 1
        return name

    @api.onchange("team_id", "season_id", "competition_id")
    def _onchange_scope_fields(self):
        """Handle onchange scope fields."""
        for record in self:
            generated_name = record._get_generated_name(record=record)
            if generated_name:
                record.name = generated_name

    @api.depends("line_ids")
    def _compute_line_count(self):
        """Compute line count."""
        for record in self:
            record.line_count = len(record.line_ids)

    @api.depends("match_sheet_ids")
    def _compute_match_sheet_count(self):
        """Compute match sheet count."""
        for record in self:
            record.match_sheet_count = len(record.match_sheet_ids)

    @api.depends(
        "status",
        "valid_from",
        "valid_to",
        "rule_set_id",
        "competition_id",
        "competition_id.rule_set_id",
        "min_players_required",
        "max_players_allowed",
        "line_ids",
        "line_ids.status",
        "line_ids.date_from",
        "line_ids.date_to",
        "line_ids.player_id",
        "line_ids.player_id.gender",
        "line_ids.player_id.state",
        "line_ids.player_id.birth_date",
        "line_ids.license_id",
        "line_ids.license_id.state",
        "line_ids.license_id.issue_date",
        "line_ids.license_id.expiry_date",
        "line_ids.license_id.season_id",
        "line_ids.license_id.club_id",
    )
    def _compute_readiness(self):
        """Compute readiness."""
        for record in self:
            issues = record._get_readiness_issues()
            record.ready_for_activation = not bool(issues)
            record.readiness_feedback = "\n".join(issues) if issues else False

    @api.depends(
        "match_sheet_ids.state",
        "match_sheet_ids.name",
        "match_sheet_ids.match_id",
        "match_sheet_ids.match_id.date_scheduled",
    )
    def _compute_match_day_lock(self):
        """Compute match day lock."""
        state_labels = dict(
            self.env["federation.match.sheet"]._fields["state"].selection
        )
        for record in self:
            locking_sheets = record._get_locking_match_sheets()
            record.match_day_locked = bool(locking_sheets)
            if locking_sheets:
                names = ", ".join(
                    "%s (%s)"
                    % (sheet.display_name, state_labels.get(sheet.state, sheet.state))
                    for sheet in locking_sheets
                )
                record.match_day_lock_feedback = _(
                    "Roster scope is locked because these match sheets already left draft: %(sheets)s."
                ) % {"sheets": names}
            else:
                record.match_day_lock_feedback = False

    @api.constrains("valid_from", "valid_to")
    def _check_valid_dates(self):
        """Validate valid dates."""
        for record in self:
            if record.valid_from and record.valid_to:
                if record.valid_to < record.valid_from:
                    raise ValidationError(
                        _("Valid To date cannot be before Valid From date.")
                    )

    @api.constrains("season_registration_id", "team_id", "season_id")
    def _check_season_registration_consistency(self):
        """Validate season registration consistency."""
        for record in self:
            if record.season_registration_id:
                if record.season_registration_id.team_id != record.team_id:
                    raise ValidationError(
                        _("Season registration must belong to the same team.")
                    )
                if record.season_registration_id.season_id != record.season_id:
                    raise ValidationError(
                        _("Season registration must belong to the same season.")
                    )

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        for vals in vals_list:
            if not vals.get("rule_set_id") and vals.get("competition_id"):
                competition = self.env["federation.competition"].browse(
                    vals["competition_id"]
                )
                if competition.rule_set_id:
                    vals["rule_set_id"] = competition.rule_set_id.id
            if not vals.get("name"):
                vals["name"] = self._get_generated_name(vals=vals)
        records = super().create(vals_list)
        for record in records:
            record._log_audit_event(
                "roster_created",
                _(
                    "Roster '%(roster)s' created for team '%(team)s' in season '%(season)s'."
                )
                % {
                    "roster": record.display_name,
                    "team": record.team_id.display_name,
                    "season": record.season_id.display_name,
                },
            )
        return records

    def write(self, vals):
        """Update records with module-specific side effects."""
        self._assert_scope_editable_for_match_day(vals)
        self._assert_unique_active_roster(vals)
        if not vals.get("rule_set_id") and vals.get("competition_id"):
            competition = self.env["federation.competition"].browse(
                vals["competition_id"]
            )
            if competition.rule_set_id:
                vals["rule_set_id"] = competition.rule_set_id.id
        vals = dict(vals)
        force_generated_name = "name" in vals and not vals["name"]
        if force_generated_name:
            vals.pop("name")

        scope_fields = {"team_id", "season_id", "competition_id"}
        if (
            scope_fields.intersection(vals) or force_generated_name
        ) and "name" not in vals:
            result = True
            for record in self:
                record_vals = dict(vals)
                record_vals["name"] = record._get_generated_name(
                    vals=record_vals,
                    record=record,
                )
                result = (
                    super(FederationTeamRoster, record).write(record_vals) and result
                )
        else:
            result = super().write(vals)
        tracked_fields = {
            "team_id",
            "season_id",
            "competition_id",
            "season_registration_id",
            "rule_set_id",
            "valid_from",
            "valid_to",
            "min_players_required",
            "max_players_allowed",
            "notes",
        }
        changed_fields = sorted(tracked_fields.intersection(vals))
        if changed_fields:
            field_labels = ", ".join(
                self._fields[field].string for field in changed_fields
            )
            for record in self:
                record._log_audit_event(
                    "roster_updated",
                    _("Roster updated: %(fields)s.") % {"fields": field_labels},
                )
        return result

    def action_view_lines(self):
        """Execute the view lines action."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Roster Lines"),
            "res_model": "federation.team.roster.line",
            "view_mode": "list,form",
            "domain": [("roster_id", "=", self.id)],
            "context": {"default_roster_id": self.id},
        }

    def action_view_match_sheets(self):
        """Execute the view match sheets action."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Match Sheets"),
            "res_model": "federation.match.sheet",
            "view_mode": "list,form",
            "domain": [("roster_id", "=", self.id)],
            "context": {"default_roster_id": self.id},
        }

    def _get_effective_rule_set(self):
        """Return effective rule set."""
        self.ensure_one()
        return self.rule_set_id or (
            self.competition_id.rule_set_id
            if self.competition_id and self.competition_id.rule_set_id
            else self.env["federation.rule.set"]
        )

    def _get_locking_match_sheets(self):
        """Return locking match sheets."""
        self.ensure_one()
        return self.match_sheet_ids.filtered(
            lambda sheet: sheet.state in ("submitted", "approved", "locked")
        )

    def _log_audit_event(
        self, event_type, description, player=False, match_sheet=False
    ):
        """Handle log audit event."""
        Audit = self.env.get("federation.participation.audit")
        if Audit is None:
            return False
        for record in self:
            Audit.create_event(
                event_type=event_type,
                description=description,
                team=record.team_id,
                roster=record,
                match_sheet=match_sheet,
                player=player,
            )
        return True

    def _assert_unique_active_roster(self, vals):
        """Raise ValidationError if activating would create a duplicate active roster."""
        if vals.get("status") != "active":
            return
        for record in self:
            team_id = vals.get("team_id", record.team_id.id)
            season_id = vals.get("season_id", record.season_id.id)
            competition_id = vals.get(
                "competition_id",
                record.competition_id.id if record.competition_id else False,
            )
            duplicate = self.search(
                [
                    ("team_id", "=", team_id),
                    ("season_id", "=", season_id),
                    ("competition_id", "=", competition_id),
                    ("status", "=", "active"),
                    ("id", "!=", record.id),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _(
                        "Team '%(team)s' already has an active roster for this season/competition: '%(duplicate)s'."
                    )
                    % {
                        "team": record.team_id.display_name,
                        "duplicate": duplicate.display_name,
                    }
                )

    def _assert_scope_editable_for_match_day(self, vals):
        """Handle assert scope editable for match day."""
        if self.env.context.get("bypass_match_day_lock"):
            return
        protected_fields = {
            "team_id",
            "season_id",
            "competition_id",
            "season_registration_id",
            "rule_set_id",
            "valid_from",
            "valid_to",
            "min_players_required",
            "max_players_allowed",
        }
        changed_fields = sorted(protected_fields.intersection(vals))
        if not changed_fields:
            return
        field_labels = ", ".join(self._fields[field].string for field in changed_fields)
        for record in self:
            if record.match_day_locked:
                raise ValidationError(
                    _(
                        "Roster '%(roster)s' cannot change %(fields)s because submitted, approved, or locked match sheets already reference it."
                    )
                    % {
                        "roster": record.display_name,
                        "fields": field_labels,
                    }
                )

    def _get_reference_date(self):
        """Return reference date."""
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.valid_from and self.valid_from > today:
            return self.valid_from
        if (
            self.season_id
            and self.season_id.date_start
            and self.season_id.date_start > today
        ):
            return self.season_id.date_start
        return today

    def _get_required_player_bounds(self):
        """Return required player bounds."""
        self.ensure_one()
        rule_set = self._get_effective_rule_set()
        min_required = self.min_players_required or (
            rule_set.squad_min_size if rule_set else 0
        )
        max_allowed = self.max_players_allowed or (
            rule_set.squad_max_size if rule_set else 0
        )
        return min_required, max_allowed

    def _get_readiness_issues(self, reference_date=None):
        """Return readiness issues."""
        self.ensure_one()
        reference_date = reference_date or self._get_reference_date()
        issues = []

        if self.valid_from and reference_date < self.valid_from:
            issues.append(
                _("Roster is not valid yet on %(date)s.") % {"date": self.valid_from}
            )
        if self.valid_to and reference_date > self.valid_to:
            issues.append(
                _("Roster expired before %(date)s.") % {"date": reference_date}
            )

        active_lines = self.line_ids.filtered(lambda line: line.status == "active")
        if not active_lines:
            issues.append(_("Add at least one active roster line before activation."))

        eligible_active_count = 0
        for line in active_lines:
            reasons = line._get_eligibility_reasons(reference_date=reference_date)
            if reasons:
                issues.append(
                    _("Player '%(player)s': %(reasons)s")
                    % {
                        "player": line.player_id.display_name,
                        "reasons": "; ".join(reasons),
                    }
                )
            else:
                eligible_active_count += 1

        min_required, max_allowed = self._get_required_player_bounds()
        if min_required and eligible_active_count < min_required:
            issues.append(
                _(
                    "Eligible active players (%(actual)s) are below the required minimum of %(expected)s."
                )
                % {"actual": eligible_active_count, "expected": min_required}
            )
        if max_allowed and len(active_lines) > max_allowed:
            issues.append(
                _(
                    "Active roster lines (%(actual)s) exceed the allowed maximum of %(expected)s."
                )
                % {"actual": len(active_lines), "expected": max_allowed}
            )

        return issues

    def action_set_draft(self):
        """Execute the set draft action."""
        for record in self:
            if record.match_day_locked:
                raise ValidationError(
                    _(
                        "Roster '%(roster)s' cannot return to draft after match-day sheets have already left draft."
                    )
                    % {"roster": record.display_name}
                )
        self.write({"status": "draft"})

    def action_activate(self):
        """Execute the activate action."""
        for record in self:
            issues = record._get_readiness_issues()
            if issues:
                raise ValidationError(
                    _("Roster '%(roster)s' is not ready to activate:\n- %(issues)s")
                    % {
                        "roster": record.display_name,
                        "issues": "\n- ".join(issues),
                    }
                )
        self.write({"status": "active"})
        for record in self:
            record._log_audit_event(
                "roster_activated",
                _("Roster '%(roster)s' activated for competition operations.")
                % {"roster": record.display_name},
            )

    def action_close(self):
        """Execute the close action."""
        self.with_context(bypass_match_day_lock=True).write({"status": "closed"})
        for record in self:
            record._log_audit_event(
                "roster_closed",
                _("Roster '%(roster)s' closed.") % {"roster": record.display_name},
            )
