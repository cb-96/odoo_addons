from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FederationMatchSheetLine(models.Model):
    _name = "federation.match.sheet.line"
    _description = "Match Sheet Line"

    match_sheet_id = fields.Many2one(
        "federation.match.sheet",
        string="Match Sheet",
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
    roster_line_id = fields.Many2one(
        "federation.team.roster.line",
        string="Roster Line",
        ondelete="set null",
    )
    is_starter = fields.Boolean(string="Is Starter", default=False)
    is_substitute = fields.Boolean(string="Is Substitute", default=False)
    is_captain = fields.Boolean(string="Is Captain", default=False)
    jersey_number = fields.Char(string="Jersey Number")
    entered_minute = fields.Integer(string="Entered Minute")
    left_minute = fields.Integer(string="Left Minute")
    notes = fields.Text(string="Notes")
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

    _unique_match_sheet_player = models.Constraint(
        'UNIQUE(match_sheet_id, player_id)',
        'A player cannot appear twice on the same match sheet.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        self._assert_parent_sheets_allow_new_lines(vals_list)
        records = super().create(vals_list)
        for record in records:
            record.match_sheet_id._log_audit_event(
                "sheet_line_added",
                _("Player '%(player)s' added to the match sheet.")
                % {"player": record.player_id.display_name},
                player=record.player_id,
            )
        return records

    def write(self, vals):
        """Update records with module-specific side effects."""
        self._assert_parent_sheet_line_editable(vals)
        result = super().write(vals)
        if {"entered_minute", "left_minute"} & set(vals):
            for record in self:
                minute_bits = []
                if record.entered_minute:
                    minute_bits.append(
                        _("entered in minute %(minute)s")
                        % {"minute": record.entered_minute}
                    )
                if record.left_minute:
                    minute_bits.append(
                        _("left in minute %(minute)s")
                        % {"minute": record.left_minute}
                    )
                record.match_sheet_id._log_audit_event(
                    "substitution_recorded",
                    _("Substitution updated for '%(player)s': %(details)s.")
                    % {
                        "player": record.player_id.display_name,
                        "details": ", ".join(minute_bits) or _("no minute recorded"),
                    },
                    player=record.player_id,
                )
        else:
            tracked_fields = {
                "player_id",
                "roster_line_id",
                "is_starter",
                "is_substitute",
                "is_captain",
                "jersey_number",
                "notes",
            }
            changed_fields = sorted(tracked_fields.intersection(vals))
            if changed_fields:
                field_labels = ", ".join(self._fields[field].string for field in changed_fields)
                for record in self:
                    record.match_sheet_id._log_audit_event(
                        "sheet_line_updated",
                        _("Match-sheet line for '%(player)s' updated: %(fields)s.")
                        % {
                            "player": record.player_id.display_name,
                            "fields": field_labels,
                        },
                        player=record.player_id,
                    )
        return result

    def unlink(self):
        """Delete records after applying module-specific safeguards."""
        self._assert_parent_sheet_line_editable()
        audit_payloads = [
            (
                record.match_sheet_id,
                record.player_id,
                _("Player '%(player)s' removed from the match sheet.")
                % {"player": record.player_id.display_name},
            )
            for record in self
        ]
        result = super().unlink()
        for sheet, player, description in audit_payloads:
            sheet._log_audit_event(
                "sheet_line_removed",
                description,
                player=player,
            )
        return result

    @api.depends(
        "player_id",
        "roster_line_id",
        "roster_line_id.eligible",
        "roster_line_id.eligibility_feedback",
        "roster_line_id.status",
        "roster_line_id.date_from",
        "roster_line_id.date_to",
        "match_sheet_id",
        "match_sheet_id.roster_id",
        "match_sheet_id.team_id",
        "match_sheet_id.match_id",
        "match_sheet_id.match_id.date_scheduled",
        "match_sheet_id.match_id.tournament_id",
    )
    def _compute_eligible(self):
        """Compute eligible."""
        for record in self:
            reasons = record._get_eligibility_reasons()
            record.eligible = not bool(reasons)
            record.eligibility_feedback = "\n".join(reasons) if reasons else False

    def _assert_parent_sheets_allow_new_lines(self, vals_list):
        """Handle assert parent sheets allow new lines."""
        sheet_ids = [vals.get("match_sheet_id") for vals in vals_list if vals.get("match_sheet_id")]
        sheets = self.env["federation.match.sheet"].browse(sheet_ids)
        for sheet in sheets:
            if sheet.state in ("approved", "locked"):
                raise ValidationError(
                    _(
                        "Cannot add players to match sheet '%(sheet)s' once it is approved or locked."
                    )
                    % {"sheet": sheet.display_name}
                )

    def _assert_parent_sheet_line_editable(self, vals=None):
        """Handle assert parent sheet line editable."""
        for record in self:
            if record.match_sheet_id.state == "locked":
                raise ValidationError(
                    _("Locked match sheets cannot be modified.")
                )
            if record.match_sheet_id.state == "approved":
                allowed_fields = {"entered_minute", "left_minute", "notes"}
                if vals is None or any(field not in allowed_fields for field in vals):
                    raise ValidationError(
                        _(
                            "Approved match sheets cannot change player selection or lineup roles. Record substitutions instead."
                        )
                    )

    @api.constrains("is_starter", "is_substitute")
    def _check_starter_substitute(self):
        """Validate starter substitute."""
        for record in self:
            if record.is_starter and record.is_substitute:
                raise ValidationError(
                    _("A player cannot be both a starter and a substitute.")
                )

    @api.constrains("entered_minute", "left_minute", "is_starter", "is_substitute")
    def _check_substitution_governance(self):
        """Validate substitution governance."""
        for record in self:
            entered_minute = record.entered_minute or False
            left_minute = record.left_minute or False

            if entered_minute:
                if entered_minute <= 0:
                    raise ValidationError(
                        _("Entered minute must be a positive number.")
                    )
                if not record.is_substitute:
                    raise ValidationError(
                        _("Only substitute lines can record an entered minute.")
                    )
            if left_minute:
                if left_minute <= 0:
                    raise ValidationError(
                        _("Left minute must be a positive number.")
                    )
                if not (record.is_starter or entered_minute):
                    raise ValidationError(
                        _(
                            "Only starters or players who entered from the bench can record a left minute."
                        )
                    )
            if entered_minute and left_minute:
                if left_minute <= entered_minute:
                    raise ValidationError(
                        _("A player cannot leave before or at the same minute they entered.")
                    )

    @api.constrains("roster_line_id", "match_sheet_id")
    def _check_roster_line_consistency(self):
        """Validate roster line consistency."""
        for record in self:
            if record.roster_line_id and record.match_sheet_id.roster_id:
                if record.roster_line_id.roster_id != record.match_sheet_id.roster_id:
                    raise ValidationError(
                        _("Roster line must belong to the match sheet's roster.")
                    )

    def _get_eligibility_reasons(self):
        """Return eligibility reasons."""
        self.ensure_one()
        if not self.player_id or not self.match_sheet_id:
            return []

        sheet = self.match_sheet_id
        reference_date = sheet._get_reference_date()
        reasons = []

        if sheet.roster_id and not self.roster_line_id:
            reasons.append(_("Select a roster line from the chosen roster."))

        if self.roster_line_id:
            if self.roster_line_id.player_id != self.player_id:
                reasons.append(_("Selected roster line does not belong to the chosen player."))
            if self.roster_line_id.status != "active":
                reasons.append(_("Selected roster line is not active."))
            if self.roster_line_id.date_from and reference_date < self.roster_line_id.date_from:
                reasons.append(
                    _("Selected roster line is not active before %(date)s.")
                    % {"date": self.roster_line_id.date_from}
                )
            if self.roster_line_id.date_to and reference_date > self.roster_line_id.date_to:
                reasons.append(
                    _("Selected roster line expired after %(date)s.")
                    % {"date": self.roster_line_id.date_to}
                )
            if self.roster_line_id.team_id and self.roster_line_id.team_id != sheet.team_id:
                reasons.append(_("Selected roster line belongs to a different team."))
            if self.roster_line_id.eligibility_feedback:
                reasons.extend(self.roster_line_id.eligibility_feedback.splitlines())

        service = self.env.get("federation.eligibility.service")
        rule_set = sheet._get_effective_rule_set()
        if service is not None and rule_set:
            context = {
                "match_date": reference_date,
                "tournament_id": sheet.match_id.tournament_id.id if sheet.match_id.tournament_id else None,
                "season_id": sheet.match_id.tournament_id.season_id.id if sheet.match_id.tournament_id and sheet.match_id.tournament_id.season_id else None,
                "team_id": sheet.team_id.id if sheet.team_id else None,
                "club_id": sheet.team_id.club_id.id if sheet.team_id and sheet.team_id.club_id else None,
            }
            if self.roster_line_id and self.roster_line_id.license_id:
                context["license_id"] = self.roster_line_id.license_id.id
            result = service.check_player_eligibility(self.player_id, rule_set, context=context)
            reasons.extend(result.get("reasons", []))
        return reasons
