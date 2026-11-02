from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_HANDOFF_TOKEN = object()


class FederationFinanceEvent(models.Model):
    _name = "federation.finance.event"
    _description = "Federation Finance Event"
    _check_company_auto = True
    company_id = fields.Many2one('res.company', required=True, index=True, default=lambda self: self.env.company)
    _inherit = [
        "federation.finance.event.export.mixin",
        "mail.thread",
        "mail.activity.mixin",
    ]
    _order = "create_date desc"

    name = fields.Char(required=True)
    fee_type_id = fields.Many2one(
        "federation.fee.type",
        check_company=True,
        required=True,
        ondelete="restrict",
    )
    event_type = fields.Selection(
        [
            ("charge", "Charge"),
            ("credit", "Credit"),
            ("reimbursement", "Reimbursement"),
        ],
        required=True,
    )
    amount = fields.Monetary(
        currency_field="currency_id",
        required=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("settled", "Settled"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
    )
    source_model = fields.Char(required=True)
    source_res_id = fields.Integer(required=True)
    season_id = fields.Many2one(
        "federation.season",
        ondelete="set null",
        index=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        ondelete="set null",
    )
    club_id = fields.Many2one(
        "federation.club",
        ondelete="set null",
    )
    player_id = fields.Many2one(
        "federation.player",
        ondelete="set null",
    )
    referee_id = fields.Many2one(
        "federation.referee",
        ondelete="set null",
    )
    invoice_ref = fields.Char()
    external_ref = fields.Char()
    notes = fields.Text()
    handoff_state = fields.Selection(
        [
            ("pending_export", "Pending Export"),
            ("exported", "Exported"),
            ("reconciled", "Reconciled"),
            ("closed", "Closed"),
        ],
        default="pending_export",
        required=True,
    )
    export_schema_version = fields.Char(
        default="finance_event_v1",
        required=True,
        readonly=True,
    )
    accounting_batch_ref = fields.Char()
    reconciliation_ref = fields.Char()
    closure_note = fields.Text()
    exported_on = fields.Datetime(readonly=True)
    exported_by_id = fields.Many2one("res.users", readonly=True)
    reconciled_on = fields.Datetime(readonly=True)
    reconciled_by_id = fields.Many2one("res.users", readonly=True)
    closed_on = fields.Datetime(readonly=True)
    closed_by_id = fields.Many2one("res.users", readonly=True)

    _fee_source_unique = models.Constraint(
        "unique (company_id, fee_type_id, source_model, source_res_id)",
        "A finance event already exists for this fee type and source record.",
    )

    @api.model
    def _resolve_source_record(self, source_model, source_res_id):
        """Resolve source record."""
        if not source_model or not source_res_id:
            return (
                self.env[source_model].browse()
                if source_model
                else self.env["federation.season"].browse()
            )
        model = self.env.get(source_model)
        if model is None:
            return self.env["federation.season"].browse()
        return model.browse(source_res_id).exists()

    @api.model
    def _resolve_path_value(self, record, path):
        """Resolve path value."""
        value = record
        for attribute in path.split("."):
            value = getattr(value, attribute, False)
            if not value:
                return False
        return value

    @api.model
    def _infer_season_from_source(self, source_record):
        """Infer season from source."""
        if not source_record:
            return self.env["federation.season"].browse()

        for path in (
            "season_id",
            "tournament_id.season_id",
            "match_id.tournament_id.season_id",
            "participant_id.tournament_id.season_id",
            "registration_id.season_id",
            "round_id.tournament_id.season_id",
            "case_id.match_id.tournament_id.season_id",
        ):
            season = self._resolve_path_value(source_record, path)
            if season and getattr(season, "_name", False) == "federation.season":
                return season
        return self.env["federation.season"].browse()

    @api.model
    def _infer_season_from_vals(self, vals):
        """Infer season from vals."""
        source_model = vals.get("source_model")
        source_res_id = vals.get("source_res_id")
        source_record = self._resolve_source_record(source_model, source_res_id)
        return self._infer_season_from_source(source_record)

    @api.model_create_multi
    def create(self, vals_list):
        """Create records with module-specific defaults and side effects."""
        prepared_vals_list = []
        for vals in vals_list:
            prepared_vals = dict(vals)
            if not prepared_vals.get("season_id"):
                season = self._infer_season_from_vals(prepared_vals)
                if season:
                    prepared_vals["season_id"] = season.id
            prepared_vals_list.append(prepared_vals)
        return super().create(prepared_vals_list)

    @api.constrains("amount")
    def _check_amount(self):
        """Validate amount."""
        for record in self:
            if record.amount < 0:
                raise ValidationError("Amount must be >= 0.")

    @api.constrains("source_model")
    def _check_source_model(self):
        """Validate source model."""
        for record in self:
            if not record.source_model:
                raise ValidationError("Source model must not be empty.")

    @api.constrains("source_res_id")
    def _check_source_res_id(self):
        """Validate source res ID."""
        for record in self:
            if record.source_res_id <= 0:
                raise ValidationError("Source res ID must be > 0.")

    def _finance_lock(self):
        self.check_access('write')
        if self:
            self.flush_recordset()
            self.env.cr.execute('SELECT id FROM federation_finance_event WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(self.ids)])
            self.invalidate_recordset()
            self.check_access('write')

    @api.constrains('company_id', 'fee_type_id', 'source_model', 'source_res_id', 'partner_id')
    def _check_finance_company(self):
        for event in self:
            if event.fee_type_id.company_id != event.company_id:
                raise ValidationError(_('Fee and obligation must belong to the same company.'))
            if event.partner_id.company_id and event.partner_id.company_id != event.company_id:
                raise ValidationError(_('The payer belongs to another company.'))
            source = event._resolve_source_record(event.source_model, event.source_res_id)
            if source and 'company_id' in source._fields and source.company_id and source.company_id != event.company_id:
                raise ValidationError(_('The source belongs to another company.'))

    @api.model_create_multi
    def create(self, vals_list):
        audit = ('exported_on', 'exported_by_id', 'reconciled_on', 'reconciled_by_id', 'closed_on', 'closed_by_id')
        if any(v.get('state', 'draft') not in ('draft', 'confirmed')
               or v.get('handoff_state', 'pending_export') != 'pending_export'
               or any(v.get(k) for k in audit) for v in vals_list):
            raise AccessError(_('Create an obligation without forged lifecycle metadata.'))
        return super().create(vals_list)

    def _write_handoff(self, vals):
        return self.with_context(finance_handoff_token=_HANDOFF_TOKEN).write(vals)

    def write(self, vals):
        audit = {'handoff_state', 'exported_on', 'exported_by_id', 'reconciled_on', 'reconciled_by_id', 'closed_on', 'closed_by_id'}
        if audit & set(vals) and self.env.context.get('finance_handoff_token') is not _HANDOFF_TOKEN:
            raise AccessError(_('Use the accounting handoff commands.'))
        self._finance_lock()
        identity = {'company_id', 'fee_type_id', 'source_model', 'source_res_id', 'amount', 'currency_id', 'partner_id', 'event_type'}
        allowed = {'draft': {'draft', 'confirmed', 'cancelled'}, 'confirmed': {'confirmed', 'settled', 'cancelled'},
                   'settled': {'settled'}, 'cancelled': {'cancelled'}}
        for event in self:
            if identity & set(vals) and event.state != 'draft':
                raise ValidationError(_('Confirmed obligation identity and amount are immutable.'))
            target = vals.get('state', event.state)
            reversal = target == 'cancelled' and event.state == 'settled' and hasattr(event, '_invoice_resolved') and event._invoice_resolved()
            if not reversal and target not in allowed[event.state]:
                raise ValidationError(_('Invalid obligation lifecycle transition.'))
        return super().write(vals)

    def action_confirm(self):
        """Execute the confirm action."""
        self._finance_lock()
        for record in self:
            if record.state != "draft":
                raise ValidationError("Only draft events can be confirmed.")
            record.write({"state": "confirmed"})
            record.flush_recordset()
            Dispatcher = record.env.get("federation.notification.dispatcher")
            if Dispatcher is not None:
                Dispatcher.send_finance_event_confirmed(record)

    def action_settle(self):
        """Execute the settle action."""
        self._finance_lock()
        for record in self:
            if record.state != "confirmed":
                raise ValidationError("Only confirmed events can be settled.")
            record.write({"state": "settled"})
            record.flush_recordset()

    def action_cancel(self):
        """Execute the cancel action."""
        self._finance_lock()
        for record in self:
            if record.state == "settled":
                raise ValidationError("Settled events cannot be cancelled.")
            record._write_handoff(
                {
                    "state": "cancelled",
                    "handoff_state": "closed",
                    "closed_on": fields.Datetime.now(),
                    "closed_by_id": self.env.user.id,
                }
            )
            record.flush_recordset()

    def action_mark_exported(self):
        """Execute the mark exported action."""
        self._finance_lock()
        for record in self:
            if record.state not in ("confirmed", "settled"):
                raise ValidationError(
                    "Only confirmed or settled finance events can be exported."
                )
            if record.handoff_state == "closed":
                raise ValidationError(
                    "Closed handoff records cannot be exported again."
                )
            record._write_handoff(
                {
                    "handoff_state": "exported",
                    "exported_on": fields.Datetime.now(),
                    "exported_by_id": self.env.user.id,
                }
            )
            record.flush_recordset()

    def action_mark_reconciled(self):
        """Execute the mark reconciled action."""
        self._finance_lock()
        for record in self:
            if record.state != "settled":
                raise ValidationError(
                    "Only settled finance events can be marked as reconciled."
                )
            if record.handoff_state not in ("exported", "reconciled"):
                raise ValidationError(
                    "Mark the event as exported before reconciling it with the accounting system."
                )
            record._write_handoff(
                {
                    "handoff_state": "reconciled",
                    "reconciled_on": fields.Datetime.now(),
                    "reconciled_by_id": self.env.user.id,
                }
            )
            record.flush_recordset()

    def action_close_handoff(self):
        """Execute the close handoff action."""
        self._finance_lock()
        for record in self:
            if record.state != "settled":
                raise ValidationError(
                    "Only settled finance events can close the accounting handoff."
                )
            if record.handoff_state != "reconciled":
                raise ValidationError(
                    "Reconcile the event before closing the accounting handoff."
                )
            record._write_handoff(
                {
                    "handoff_state": "closed",
                    "closed_on": fields.Datetime.now(),
                    "closed_by_id": self.env.user.id,
                }
            )
            record.flush_recordset()

    @api.model
    def _build_external_ref(self, source_record, fee_type):
        """Build external ref."""
        fee_code = (fee_type.code or str(fee_type.id)).upper()
        model_token = source_record._name.replace(".", "_")
        return f"{fee_code}-{model_token}-{source_record.id}"

    @api.model
    def _prepare_from_source_vals(
        self,
        source_record,
        fee_type,
        amount=None,
        event_type="charge",
        partner=None,
        note=None,
        extra_vals=None,
    ):
        """Prepare from source vals."""
        if amount is None:
            amount = fee_type.default_amount

        vals = {
            "name": f"{fee_type.name} - {source_record.name if hasattr(source_record, 'name') else source_record.id}",
            "fee_type_id": fee_type.id,
            "event_type": event_type,
            "amount": amount,
            "currency_id": fee_type.currency_id.id or self.env.company.currency_id.id,
            "source_model": source_record._name,
            "source_res_id": source_record.id,
            "season_id": self._infer_season_from_source(source_record).id or False,
            "partner_id": partner.id if partner else False,
            "external_ref": self._build_external_ref(source_record, fee_type),
            "export_schema_version": "finance_event_v1",
            "notes": note,
        }

        # Try to set related fields if available on source_record
        if source_record._name == "federation.club":
            vals["club_id"] = source_record.id
        elif hasattr(source_record, "club_id") and source_record.club_id:
            vals["club_id"] = source_record.club_id.id
        if source_record._name == "federation.player":
            vals["player_id"] = source_record.id
        elif hasattr(source_record, "player_id") and source_record.player_id:
            vals["player_id"] = source_record.player_id.id
        if source_record._name == "federation.referee":
            vals["referee_id"] = source_record.id
        elif hasattr(source_record, "referee_id") and source_record.referee_id:
            vals["referee_id"] = source_record.referee_id.id

        vals["company_id"] = fee_type.company_id.id

        if extra_vals:
            for key, value in extra_vals.items():
                if key in self._fields:
                    vals[key] = value

        return vals

    @api.model
    def ensure_from_source(
        self,
        source_record,
        fee_type,
        amount=None,
        event_type="charge",
        partner=None,
        note=None,
        extra_vals=None,
        update_existing=False,
    ):
        """Handle ensure from source."""
        existing = self.search(
            [
                ("fee_type_id", "=", fee_type.id),
                ("source_model", "=", source_record._name),
                ("source_res_id", "=", source_record.id),
            ],
            limit=1,
        )
        vals = self._prepare_from_source_vals(
            source_record,
            fee_type,
            amount=amount,
            event_type=event_type,
            partner=partner,
            note=note,
            extra_vals=extra_vals,
        )

        if existing:
            if update_existing and existing.state == "draft":
                update_vals = {}
                for field_name in (
                    "name",
                    "amount",
                    "currency_id",
                    "partner_id",
                    "club_id",
                    "player_id",
                    "referee_id",
                    "external_ref",
                    "notes",
                ):
                    value = vals.get(field_name)
                    existing_value = existing[field_name]
                    if self._fields[field_name].type == "many2one":
                        existing_value = existing_value.id
                    if value not in (False, None, "") and existing_value != value:
                        update_vals[field_name] = value
                if existing.state == "cancelled":
                    update_vals.update(
                        {
                            "state": "draft",
                            "handoff_state": "pending_export",
                            "closed_on": False,
                            "closed_by_id": False,
                        }
                    )
                if update_vals:
                    existing.write(update_vals)
            elif not existing.external_ref and vals.get("external_ref"):
                existing.external_ref = vals["external_ref"]
            return existing

        return self.create(vals)

    @api.model
    def create_from_source(
        self,
        source_record,
        fee_type,
        amount=None,
        event_type="charge",
        partner=None,
        note=None,
        extra_vals=None,
    ):
        """Helper to create finance event from a source record.

        Args:
            source_record: The record that triggers this finance event.
            fee_type: federation.fee.type record.
            amount: Optional amount override; defaults to fee_type.default_amount.
            event_type: "charge", "credit", or "reimbursement".
            partner: Optional res.partner record.
            note: Optional notes.

        Returns:
            The existing or newly created federation.finance.event record.
        """
        existing = self.search(
            [
                ("fee_type_id", "=", fee_type.id),
                ("source_model", "=", source_record._name),
                ("source_res_id", "=", source_record.id),
            ],
            limit=1,
        )
        if existing:
            return existing
        return self.create(
            self._prepare_from_source_vals(
                source_record,
                fee_type,
                amount=amount,
                event_type=event_type,
                partner=partner,
                note=note,
                extra_vals=extra_vals,
            )
        )

    def action_create_invoice(self):
        raise UserError(_('Install the opt-in native accounting addon. No elevated invoice fallback is supported.'))

    def action_batch_create_invoices(self):
        """Create invoices for eligible finance events and report failures.

        This server-side helper is used by the list-view server action so
        operators get a clear error summary instead of silent skips.
        """
        failures = []
        for event in self:
            if event.invoice_ref or event.state == "cancelled":
                continue
            try:
                event.action_create_invoice()
            except ValidationError as error:
                failures.append(f"{event.display_name}: {error}")
            except Exception as error:  # pylint: disable=broad-except
                failures.append(
                    _("%(event)s: unexpected error (%(error)s)")
                    % {
                        "event": event.display_name,
                        "error": error,
                    }
                )

        if failures:
            raise UserError(
                _("Some invoices could not be created:\n%(details)s")
                % {"details": "\n".join(failures)}
            )
        return True
