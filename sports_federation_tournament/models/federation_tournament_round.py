from datetime import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationTournamentRound(models.Model):
    _name = "federation.tournament.round"
    _description = "Tournament Round"
    _order = "sequence, id"

    name = fields.Char(string="Name", required=True)
    tournament_id = fields.Many2one(
        "federation.tournament",
        string="Tournament",
        related="stage_id.tournament_id",
        store=True,
    )
    stage_id = fields.Many2one(
        "federation.tournament.stage",
        string="Stage",
        required=True,
        ondelete="cascade",
    )
    group_id = fields.Many2one(
        "federation.tournament.group",
        string="Group",
        ondelete="set null",
    )
    sequence = fields.Integer(string="Sequence", default=10)
    round_date = fields.Date(string="Date")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("scheduled", "Scheduled"),
            ("completed", "Completed"),
        ],
        string="Status",
        default="draft",
        required=True,
    )
    match_ids = fields.One2many("federation.match", "round_id", string="Matches")
    match_count = fields.Integer(
        string="Match Count", compute="_compute_match_count", store=True
    )

    @api.depends("match_ids")
    def _compute_match_count(self):
        """Compute match count."""
        for rec in self:
            rec.match_count = len(rec.match_ids)

    @api.model
    def _build_default_name(self, stage, sequence, group=False):
        """Build default name."""
        if group:
            return _("%(group)s - Round %(sequence)s") % {
                "group": group.display_name,
                "sequence": sequence,
            }
        if stage:
            return _("%(stage)s - Round %(sequence)s") % {
                "stage": stage.display_name,
                "sequence": sequence,
            }
        return _("Round %(sequence)s") % {"sequence": sequence}

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        Group = self.env["federation.tournament.group"]
        Stage = self.env["federation.tournament.stage"]
        prepared_vals_list = []
        for vals in vals_list:
            prepared_vals = dict(vals)
            if not prepared_vals.get("name"):
                stage = (
                    Stage.browse(prepared_vals.get("stage_id"))
                    if prepared_vals.get("stage_id")
                    else Stage.browse([])
                )
                group = (
                    Group.browse(prepared_vals.get("group_id"))
                    if prepared_vals.get("group_id")
                    else Group.browse([])
                )
                prepared_vals["name"] = self._build_default_name(
                    stage,
                    prepared_vals.get("sequence") or 1,
                    group,
                )
            prepared_vals_list.append(prepared_vals)
        return super().create(prepared_vals_list)

    def write(self, vals):
        """Update records with module-specific side effects."""
        sync_round_dates = "round_date" in vals
        result = super().write(vals)
        if sync_round_dates:
            self._sync_match_dates_from_round()
        return result

    def _sync_match_dates_from_round(self):
        """Synchronize match dates from round."""
        for rec in self.filtered(lambda round_rec: round_rec.round_date):
            for match in rec.match_ids.filtered(
                lambda round_match: round_match._has_scheduled_time(
                    round_match.scheduled_time
                )
            ):
                target_dt = datetime.combine(
                    rec.round_date,
                    match._float_to_time(match.scheduled_time),
                )
                if (
                    not match.date_scheduled
                    or fields.Datetime.to_datetime(match.date_scheduled) != target_dt
                ):
                    match.write({"date_scheduled": target_dt})

    @api.onchange("stage_id", "group_id", "sequence")
    def _onchange_scope_defaults(self):
        """Handle onchange scope defaults."""
        for rec in self:
            if not rec.name:
                rec.name = self._build_default_name(
                    rec.stage_id, rec.sequence or 1, rec.group_id
                )

    @api.constrains("sequence", "stage_id", "group_id")
    def _check_sequence(self):
        """Validate sequence."""
        for rec in self:
            if rec.sequence < 1:
                raise ValidationError(_("Round sequence must be a positive number."))

            domain = [
                ("id", "!=", rec.id),
                ("stage_id", "=", rec.stage_id.id),
                ("sequence", "=", rec.sequence),
                ("group_id", "=", rec.group_id.id if rec.group_id else False),
            ]
            if self.search_count(domain):
                raise ValidationError(
                    _(
                        "Round sequence must be unique within the same stage and group scope."
                    )
                )

    @api.model
    def get_or_create_stage_round(self, stage, sequence, group=False, values=None):
        """Return or create stage round."""
        group = group or self.env["federation.tournament.group"]
        values = dict(values or {})
        domain = [
            ("stage_id", "=", stage.id),
            ("sequence", "=", sequence),
            ("group_id", "=", group.id if group else False),
        ]
        round_record = self.search(domain, limit=1)

        values.setdefault("stage_id", stage.id)
        values.setdefault("group_id", group.id if group else False)
        values.setdefault("sequence", sequence)
        values.setdefault(
            "name",
            self._build_default_name(stage, sequence, group),
        )

        if round_record:
            write_vals = {}
            if not round_record.name and values.get("name"):
                write_vals["name"] = values["name"]
            for field_name in ("round_date", "venue_id"):
                if (
                    field_name in values
                    and field_name in round_record._fields
                    and not round_record[field_name]
                ):
                    write_vals[field_name] = values[field_name]
            if write_vals:
                round_record.write(write_vals)
            return round_record

        create_vals = {
            key: value for key, value in values.items() if key in self._fields
        }
        return self.create(create_vals)

    def action_schedule(self):
        """Execute the schedule action."""
        for rec in self:
            rec.state = "scheduled"

    def action_complete(self):
        """Execute the complete action."""
        for rec in self:
            rec.state = "completed"
