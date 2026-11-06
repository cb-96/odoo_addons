"""Legal hold, governed erasure and retention for member evidence revisions.

Evidence revisions stay immutable. The only permitted changes are:

* placing or releasing a legal hold, with a recorded reason;
* erasing revisions on a documented request (for example a data-subject
  erasure request), which is refused while a legal hold applies;
* the scheduled retention run, which only starts once the federation
  configures ``sports_federation_member_services.evidence_retention_days``.

The scheduled run removes replaced revisions (an older revision of a request
that has since received a newer upload) and every revision of a cancelled
request, once the revision is older than the configured period. The revision
that is still current for an open request is never removed by the schedule.
Every hold, release, erasure and retention run is recorded.
"""

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .lifecycle import command, lock
from .membership import manager

RETENTION_PARAMETER = "sports_federation_member_services.evidence_retention_days"
RETENTION_POLICY_CODE = "member_evidence_revisions"
ERASURE_POLICY_CODE = "member_evidence_erasure"
MIN_REASON_LENGTH = 10


def evidence_retention_days_from_value(value):
    """Return ``(days, problem)``; ``days`` is ``0`` when nothing may be deleted."""
    if value in (None, False, ""):
        return 0, False
    try:
        days = int(value)
    except (TypeError, ValueError):
        return 0, "Evidence retention period %r is not a whole number of days." % (
            value,
        )
    return (days, False) if days > 0 else (0, False)


def _require_reason(reason):
    reason = (reason or "").strip()
    if len(reason) < MIN_REASON_LENGTH:
        raise ValidationError(
            _("Record a reason of at least %s characters.") % MIN_REASON_LENGTH
        )
    return reason


class EvidenceRevisionGovernance(models.Model):
    _inherit = "federation.member.evidence.revision"

    # ------------------------------------------------------------------
    # Legal hold
    # ------------------------------------------------------------------
    def _set_legal_hold(self, reason):
        manager(self.env)
        reason = _require_reason(reason)
        rows = self.sudo()
        lock(rows)
        command(rows).write(
            {
                "legal_hold": True,
                "legal_hold_reason": reason,
                "legal_hold_by_id": self.env.uid,
                "legal_hold_on": fields.Datetime.now(),
            }
        )
        rows._post_governance_note(_("Legal hold placed: %s") % reason)
        return True

    def _release_legal_hold(self, reason):
        manager(self.env)
        reason = _require_reason(reason)
        rows = self.sudo()
        lock(rows)
        if rows.filtered(lambda row: not row.legal_hold):
            raise ValidationError(_("Only held evidence can be released."))
        command(rows).write(
            {
                "legal_hold": False,
                "legal_hold_reason": False,
                "legal_hold_by_id": self.env.uid,
                "legal_hold_on": fields.Datetime.now(),
            }
        )
        rows._post_governance_note(_("Legal hold released: %s") % reason)
        return True

    # ------------------------------------------------------------------
    # Governed erasure
    # ------------------------------------------------------------------
    def _erase(self, reason):
        """Delete these revisions on a documented request."""
        manager(self.env)
        reason = _require_reason(reason)
        rows = self.sudo()
        lock(rows)
        held = rows.filtered("legal_hold")
        if held:
            raise ValidationError(
                _(
                    "%s revision(s) are under legal hold and cannot be erased. "
                    "Release the hold first."
                )
                % len(held)
            )
        started_on = fields.Datetime.now()
        count = len(rows)
        rows._post_governance_note(
            _("%(count)s evidence revision(s) erased: %(reason)s")
            % {"count": count, "reason": reason},
            per_revision=True,
        )
        command(rows).unlink()
        self.env["federation.retention.evidence"].record_execution(
            ERASURE_POLICY_CODE,
            started_on=started_on,
            candidate_count=count,
            deleted_count=count,
            attachment_count=count,
            retention_rules={"trigger": "governed_erasure", "actor_id": self.env.uid},
            operator_message=reason,
            source_model=self._name,
        )
        return count

    def _post_governance_note(self, message, per_revision=False):
        """Record the decision on each affected request without document data."""
        for request in self.mapped("request_id"):
            revisions = self.filtered(lambda row: row.request_id == request)
            body = message
            if per_revision:
                body = "%s (%s)" % (
                    message,
                    _("revision(s) %s")
                    % ", ".join(str(r) for r in sorted(revisions.mapped("revision"))),
                )
            request.sudo().message_post(body=body, subtype_xmlid="mail.mt_note")

    # ------------------------------------------------------------------
    # Scheduled retention
    # ------------------------------------------------------------------
    @api.model
    def _evidence_retention_days(self):
        value = self.env["ir.config_parameter"].sudo().get_param(RETENTION_PARAMETER)
        return evidence_retention_days_from_value(value)

    @api.model
    def _evidence_retention_candidates(self, cutoff):
        rows = self.sudo().search(
            [
                ("legal_hold", "=", False),
                ("create_date", "<", fields.Datetime.to_string(cutoff)),
            ]
        )
        return rows.filtered(
            lambda row: row.request_id.state == "cancelled"
            or row.revision < row.request_id.document_revision
        )

    @api.model
    def _purge_retained_evidence(self, reference_dt=None):
        days, problem = self._evidence_retention_days()
        if not days:
            return {"days": 0, "problem": problem, "deleted": 0, "held": 0}
        reference_dt = fields.Datetime.to_datetime(
            reference_dt or fields.Datetime.now()
        )
        cutoff = reference_dt - timedelta(days=days)
        held = self.sudo().search_count(
            [
                ("legal_hold", "=", True),
                ("create_date", "<", fields.Datetime.to_string(cutoff)),
            ]
        )
        rows = self._evidence_retention_candidates(cutoff)
        count = len(rows)
        if rows:
            rows._post_governance_note(
                _("Evidence removed after the %s-day retention period.") % days,
                per_revision=True,
            )
            command(rows).unlink()
        return {"days": days, "problem": problem, "deleted": count, "held": held}

    @api.model
    def _cron_purge_evidence(self):
        started_on = fields.Datetime.now()
        Evidence = self.env["federation.retention.evidence"]
        days, problem = self._evidence_retention_days()
        rules = {
            "parameter": RETENTION_PARAMETER,
            "days": days,
            "scope": "replaced revisions and revisions of cancelled requests",
        }
        try:
            result = self._purge_retained_evidence(started_on)
        except Exception as error:
            Evidence.record_failure_durable(
                RETENTION_POLICY_CODE,
                started_on=started_on,
                failure_count=1,
                retention_rules=rules,
                operator_message=str(error),
                source_model=self._name,
            )
            raise
        if problem:
            message = problem
        elif not days:
            message = (
                "No evidence retention period is configured; all revisions are kept."
            )
        else:
            message = (
                "Deleted %s revision(s); %s past the period kept under legal hold."
                % (result["deleted"], result["held"])
            )
        Evidence.record_execution(
            RETENTION_POLICY_CODE,
            started_on=started_on,
            candidate_count=result["deleted"] + result["held"],
            deleted_count=result["deleted"],
            skipped_count=result["held"],
            attachment_count=result["deleted"],
            failure_count=1 if problem else 0,
            status="failed" if problem else "passed",
            dry_run=not days,
            retention_rules=rules,
            operator_message=message,
            source_model=self._name,
        )
        return result


class EvidenceGovernanceWizard(models.TransientModel):
    _name = "federation.member.evidence.governance.wizard"
    _description = "Member Evidence Legal Hold and Erasure"

    revision_ids = fields.Many2many(
        "federation.member.evidence.revision",
        string="Evidence revisions",
        required=True,
    )
    operation = fields.Selection(
        [
            ("hold", "Place legal hold"),
            ("release", "Release legal hold"),
            ("erase", "Erase permanently"),
        ],
        required=True,
        default="hold",
    )
    reason = fields.Text(
        required=True,
        help="Why this decision is taken, for example the case or request reference.",
    )
    confirm_erasure = fields.Boolean(
        string="I understand erased evidence cannot be recovered"
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        context = self.env.context
        if context.get("active_model") == "federation.member.evidence.revision":
            values["revision_ids"] = [(6, 0, context.get("active_ids") or [])]
        return values

    def action_apply(self):
        self.ensure_one()
        manager(self.env)
        revisions = self.revision_ids
        if self.operation == "hold":
            revisions._set_legal_hold(self.reason)
        elif self.operation == "release":
            revisions._release_legal_hold(self.reason)
        else:
            if not self.confirm_erasure:
                raise ValidationError(
                    _("Confirm that erased evidence cannot be recovered.")
                )
            revisions._erase(self.reason)
        return {"type": "ir.actions.act_window_close"}
