from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

from .team_roster import _dedupe_reasons


class FederationTeamRosterLine(models.Model):
    _name = "federation.team.roster.line"
    _description = "Team Roster Line"

    roster_id = fields.Many2one(
        "federation.team.roster",
        string="Roster",
        required=True,
        ondelete="cascade",
        index=True,
    )
    player_id = fields.Many2one(
        "federation.player",
        string="Player",
        required=True,
        ondelete="restrict",
        index=True,
    )
    status = fields.Selection(
        [
            ("active", "Active"),
            ("inactive", "Inactive"),
            ("suspended", "Suspended"),
            ("removed", "Removed"),
        ],
        default="active",
        required=True,
    )
    date_from = fields.Date(string="Date From")
    date_to = fields.Date(string="Date To")
    jersey_number = fields.Char(string="Jersey Number")
    is_captain = fields.Boolean(string="Is Captain", default=False)
    is_vice_captain = fields.Boolean(string="Is Vice Captain", default=False)
    notes = fields.Text(string="Notes")
    license_id = fields.Many2one(
        "federation.player.license",
        string="License",
        ondelete="set null",
    )
    eligible = fields.Boolean(
        compute="_compute_eligible",
        string="Eligible",
        store=True,
    )
    eligibility_feedback = fields.Text(
        compute="_compute_eligible",
        string="Eligibility Feedback",
        store=True,
    )
    team_id = fields.Many2one(
        "federation.team",
        string="Team",
        related="roster_id.team_id",
        store=True,
    )
    season_id = fields.Many2one(
        "federation.season",
        string="Season",
        related="roster_id.season_id",
        store=True,
    )
    competition_id = fields.Many2one(
        "federation.competition",
        string="Competition",
        related="roster_id.competition_id",
        store=True,
    )

    _unique_roster_player_date_from = models.Constraint(
        "UNIQUE(roster_id, player_id, date_from)",
        "A roster line for this player with this start date already exists.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        records = super().create(vals_list)
        records._validate_player_eligibility()
        for record in records:
            record.roster_id._log_audit_event(
                "roster_line_added",
                _("Player '%(player)s' added to the roster.")
                % {"player": record.player_id.display_name},
                player=record.player_id,
            )
        return records

    def write(self, vals):
        """Update records with module-specific side effects."""
        self._assert_not_locked_for_match_day(vals)
        result = super().write(vals)
        self._validate_player_eligibility()
        tracked_fields = {
            "player_id",
            "status",
            "date_from",
            "date_to",
            "jersey_number",
            "is_captain",
            "is_vice_captain",
            "license_id",
            "notes",
        }
        changed_fields = sorted(tracked_fields.intersection(vals))
        if changed_fields:
            field_labels = ", ".join(
                self._fields[field].string for field in changed_fields
            )
            for record in self:
                record.roster_id._log_audit_event(
                    "roster_line_updated",
                    _("Roster line for '%(player)s' updated: %(fields)s.")
                    % {
                        "player": record.player_id.display_name,
                        "fields": field_labels,
                    },
                    player=record.player_id,
                )
        return result

    def unlink(self):
        """Delete records after applying module-specific safeguards."""
        self._assert_not_locked_for_match_day()
        audit_payloads = [
            (
                record.roster_id,
                record.player_id,
                _("Player '%(player)s' removed from the roster.")
                % {"player": record.player_id.display_name},
            )
            for record in self
        ]
        result = super().unlink()
        for roster, player, description in audit_payloads:
            roster._log_audit_event(
                "roster_line_removed",
                description,
                player=player,
            )
        return result

    @api.depends(
        "status",
        "date_from",
        "date_to",
        "player_id",
        "player_id.gender",
        "player_id.state",
        "player_id.birth_date",
        "license_id",
        "license_id.state",
        "license_id.issue_date",
        "license_id.expiry_date",
        "license_id.season_id",
        "license_id.club_id",
        "roster_id",
        "roster_id.team_id",
        "roster_id.team_id.gender",
        "roster_id.season_id",
        "roster_id.club_id",
        "roster_id.competition_id",
        "roster_id.rule_set_id",
    )
    def _compute_eligible(self):
        """Compute eligible."""
        for record in self:
            reasons = record._get_eligibility_reasons()
            record.eligible = not bool(reasons)
            record.eligibility_feedback = "\n".join(reasons) if reasons else False

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        """Validate dates."""
        for record in self:
            if record.date_from and record.date_to:
                if record.date_to < record.date_from:
                    raise ValidationError(_("Date To cannot be before Date From."))

    @api.constrains("is_captain", "roster_id", "status")
    def _check_single_captain(self):
        """Validate single captain."""
        for record in self:
            if record.is_captain and record.status == "active":
                domain = [
                    ("roster_id", "=", record.roster_id.id),
                    ("is_captain", "=", True),
                    ("status", "=", "active"),
                    ("id", "!=", record.id),
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(
                        _("Only one active captain is allowed per roster.")
                    )

    @api.constrains("is_vice_captain", "roster_id", "status")
    def _check_single_vice_captain(self):
        """Validate single vice captain."""
        for record in self:
            if record.is_vice_captain and record.status == "active":
                domain = [
                    ("roster_id", "=", record.roster_id.id),
                    ("is_vice_captain", "=", True),
                    ("status", "=", "active"),
                    ("id", "!=", record.id),
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(
                        _("Only one active vice captain is allowed per roster.")
                    )

    @api.constrains("player_id", "roster_id")
    def _check_player_eligibility_rules(self):
        """Validate player eligibility rules."""
        self._validate_player_eligibility()

    def _get_eligibility_context(self, reference_date=None):
        """Return eligibility context."""
        self.ensure_one()
        roster = self.roster_id
        context = {"match_date": reference_date or roster._get_reference_date()}
        if roster.season_id:
            context["season_id"] = roster.season_id.id
        if roster.club_id:
            context["club_id"] = roster.club_id.id
        if roster.team_id:
            context["team_id"] = roster.team_id.id
        if roster.competition_id:
            context["competition_id"] = roster.competition_id.id
        if self.license_id:
            context["license_id"] = self.license_id.id
        return context

    def _get_locking_match_sheet_lines(self):
        """Return locking match sheet lines."""
        self.ensure_one()
        return self.env["federation.match.sheet.line"].search(
            [
                ("roster_line_id", "=", self.id),
                ("match_sheet_id.state", "in", ("submitted", "approved", "locked")),
            ]
        )

    def _assert_not_locked_for_match_day(self, vals=None):
        """Handle assert not locked for match day."""
        if self.env.context.get("bypass_match_day_lock"):
            return
        protected_fields = {
            "player_id",
            "status",
            "date_from",
            "date_to",
            "jersey_number",
            "is_captain",
            "is_vice_captain",
            "license_id",
        }
        if vals is not None and not protected_fields.intersection(vals):
            return
        for record in self:
            locking_lines = record._get_locking_match_sheet_lines()
            if locking_lines:
                sheet_names = ", ".join(
                    locking_lines.mapped("match_sheet_id").mapped("display_name")
                )
                raise ValidationError(
                    _(
                        "Roster line for player '%(player)s' is locked because it already appears on live match sheet(s): %(sheets)s."
                    )
                    % {
                        "player": record.player_id.display_name,
                        "sheets": sheet_names,
                    }
                )

    def _get_eligibility_reasons(self, reference_date=None):
        """Return eligibility reasons."""
        self.ensure_one()
        player = self.player_id
        roster = self.roster_id
        if not player or not roster:
            return []

        reference_date = reference_date or roster._get_reference_date()
        reasons = []
        team = roster.team_id

        if self.status != "active":
            reasons.append(_("Roster line is not active."))
        if self.date_from and reference_date < self.date_from:
            reasons.append(
                _("Player is not active on this roster before %(date)s.")
                % {"date": self.date_from}
            )
        if self.date_to and reference_date > self.date_to:
            reasons.append(
                _("Player is no longer active on this roster after %(date)s.")
                % {"date": self.date_to}
            )

        if team and team.gender in ("male", "female"):
            if not player.gender:
                reasons.append(
                    _(
                        "Player '%(player)s' must have a gender set to join team '%(team)s'."
                    )
                    % {"player": player.display_name, "team": team.display_name}
                )
            elif player.gender != team.gender:
                reasons.append(
                    _(
                        "Player '%(player)s' (%(player_gender)s) is not eligible for team '%(team)s' (%(team_gender)s)."
                    )
                    % {
                        "player": player.display_name,
                        "player_gender": player.gender,
                        "team": team.display_name,
                        "team_gender": team.gender,
                    }
                )

        Service = self.env.get("federation.eligibility.service")
        rule_set = roster._get_effective_rule_set()
        if Service is not None and rule_set:
            result = Service.check_player_eligibility(
                player,
                rule_set,
                context=self._get_eligibility_context(reference_date=reference_date),
            )
            reasons.extend(result.get("reasons", []))

        return _dedupe_reasons(reasons)

    def _validate_player_eligibility(self):
        """Validate direct team compatibility and rule-set eligibility."""
        for record in self:
            reasons = record._get_eligibility_reasons()
            if not reasons:
                continue
            raise ValidationError(
                _("Player '%(player)s' is not eligible for this roster: %(reasons)s")
                % {
                    "player": record.player_id.display_name,
                    "reasons": "; ".join(reasons),
                }
            )
