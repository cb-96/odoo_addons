from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationFinanceEventExportMixin(models.AbstractModel):
    """Mixin providing cursor-based export serialisation for finance events.

    Keeping this separate from the state-transition logic in
    FederationFinanceEvent allows each concern to evolve independently as
    more finance workflows are introduced.
    """

    _name = "federation.finance.event.export.mixin"
    _description = "Finance Event Export Mixin"

    HANDOFF_EXPORT_DEFAULT_LIMIT = 200
    HANDOFF_EXPORT_MAX_LIMIT = 500
    HANDOFF_STATE_SELECTION = [
        ("pending_export", "Pending Export"),
        ("exported", "Exported"),
        ("reconciled", "Reconciled"),
        ("closed", "Closed"),
    ]
    EXPORT_SCHEMA_VERSION = "finance_event_v1"

    @api.model
    def get_handoff_export_headers(self):
        """Return column headers for the CSV/batch export."""
        return [
            "Schema Version",
            "Event ID",
            "Name",
            "State",
            "Handoff State",
            "Event Type",
            "Amount",
            "Currency",
            "Fee Type",
            "Accounting Batch Ref",
            "Reconciliation Ref",
            "Invoice Ref",
            "External Ref",
            "Source Model",
            "Source Record ID",
            "Partner",
            "Club",
            "Player",
            "Referee",
            "Exported On",
            "Reconciled On",
            "Closed On",
            "Closure Note",
        ]

    def get_handoff_export_row(self):
        """Return one row of values matching get_handoff_export_headers()."""
        self.ensure_one()
        return [
            self.export_schema_version,
            self.id,
            self.name,
            self.state,
            self.handoff_state,
            self.event_type,
            self.amount,
            self.currency_id.name if self.currency_id else "",
            self.fee_type_id.code if self.fee_type_id else "",
            self.accounting_batch_ref or "",
            self.reconciliation_ref or "",
            self.invoice_ref or "",
            self.external_ref or "",
            self.source_model,
            self.source_res_id,
            self.partner_id.display_name if self.partner_id else "",
            self.club_id.name if self.club_id else "",
            self.player_id.display_name if self.player_id else "",
            self.referee_id.display_name if self.referee_id else "",
            fields.Datetime.to_string(self.exported_on) if self.exported_on else "",
            fields.Datetime.to_string(self.reconciled_on) if self.reconciled_on else "",
            fields.Datetime.to_string(self.closed_on) if self.closed_on else "",
            self.closure_note or "",
        ]

    @api.model
    def _normalize_handoff_export_limit(self, limit=None):
        """Return a bounded page size for cursor-based exports."""
        if limit in (False, None, ""):
            return self.HANDOFF_EXPORT_DEFAULT_LIMIT
        try:
            export_limit = int(limit)
        except (TypeError, ValueError) as error:
            raise ValidationError(
                "Finance event export limits must be positive integers."
            ) from error
        if export_limit < 1:
            raise ValidationError(
                "Finance event export limits must be positive integers."
            )
        return min(export_limit, self.HANDOFF_EXPORT_MAX_LIMIT)

    @api.model
    def _parse_handoff_export_cursor(self, cursor):
        """Parse a cursor token into its stable sort components."""
        if not cursor:
            return False
        create_date_token, separator, record_id_token = (cursor or "").partition("|")
        if not separator:
            raise ValidationError(
                "Finance event export cursors must use the '<timestamp>|<id>' format."
            )
        create_date = fields.Datetime.to_datetime(create_date_token.strip())
        try:
            record_id = int(record_id_token)
        except (TypeError, ValueError) as error:
            raise ValidationError(
                "Finance event export cursors must use the '<timestamp>|<id>' format."
            ) from error
        if not create_date or record_id < 1:
            raise ValidationError(
                "Finance event export cursors must use the '<timestamp>|<id>' format."
            )
        return {
            "create_date": fields.Datetime.to_string(create_date),
            "id": record_id,
        }

    @api.model
    def _build_handoff_export_cursor(self, event):
        """Return the cursor token that resumes after the given event."""
        event.ensure_one()
        return f"{fields.Datetime.to_string(event.create_date)}|{event.id}"

    @api.model
    def get_handoff_export_batch(self, cursor=None, limit=None):
        """Return one deterministic export batch ordered by newest events first."""
        export_limit = self._normalize_handoff_export_limit(limit=limit)
        domain = []
        parsed_cursor = self._parse_handoff_export_cursor(cursor)
        if parsed_cursor:
            domain = [
                "|",
                ("create_date", "<", parsed_cursor["create_date"]),
                "&",
                ("create_date", "=", parsed_cursor["create_date"]),
                ("id", "<", parsed_cursor["id"]),
            ]

        events = self.search(
            domain,
            order="create_date desc, id desc",
            limit=export_limit + 1,
        )
        has_more = len(events) > export_limit
        batch_events = events[:export_limit]
        next_cursor = (
            self._build_handoff_export_cursor(batch_events[-1])
            if has_more and batch_events
            else False
        )
        return {
            "events": batch_events,
            "count": len(batch_events),
            "limit": export_limit,
            "has_more": has_more,
            "next_cursor": next_cursor,
        }
