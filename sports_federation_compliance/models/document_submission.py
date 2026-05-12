import base64
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class FederationDocumentSubmission(models.Model):
    _name = "federation.document.submission"
    _description = "Federation Document Submission"
    _inherit = [
        "federation.compliance.target.mixin",
        "mail.thread",
        "mail.activity.mixin",
    ]
    _order = "create_date desc"

    STATUS_SELECTION = [
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("replacement_requested", "Replacement Requested"),
        ("expired", "Expired"),
    ]

    name = fields.Char(string="Name", required=True, tracking=True)
    requirement_id = fields.Many2one(
        "federation.document.requirement",
        string="Requirement",
        required=True,
        ondelete="restrict",
        tracking=True,
        index=True,
    )
    target_model = fields.Selection(
        string="Target Model",
        related="requirement_id.target_model",
        store=True,
    )

    # Target entity fields - exactly one must be set
    club_id = fields.Many2one(
        "federation.club",
        string="Club",
        ondelete="cascade",
        index=True,
    )
    player_id = fields.Many2one(
        "federation.player",
        string="Player",
        ondelete="cascade",
        index=True,
    )
    referee_id = fields.Many2one(
        "federation.referee",
        string="Referee",
        ondelete="cascade",
        index=True,
    )
    venue_id = fields.Many2one(
        "federation.venue",
        string="Venue",
        ondelete="cascade",
        index=True,
    )
    club_representative_id = fields.Many2one(
        "federation.club.representative",
        string="Club Representative",
        ondelete="cascade",
        index=True,
    )
    status = fields.Selection(
        selection=STATUS_SELECTION,
        string="Status",
        default="draft",
        required=True,
        tracking=True,
        index=True,
    )

    attachment_ids = fields.Many2many(
        "ir.attachment",
        string="Attachments",
    )
    issue_date = fields.Date(string="Issue Date", tracking=True)
    expiry_date = fields.Date(string="Expiry Date", tracking=True)
    reviewer_id = fields.Many2one(
        "res.users",
        string="Reviewer",
        tracking=True,
    )
    reviewed_on = fields.Datetime(string="Reviewed On", tracking=True)
    notes = fields.Text(string="Notes")

    # Computed field for display
    target_display = fields.Char(
        string="Target",
        compute="_compute_target_display",
        store=True,
    )
    target_entity_label = fields.Char(
        string="Applies To",
        compute="_compute_target_entity_label",
    )

    @api.depends(
        "club_id",
        "player_id",
        "referee_id",
        "venue_id",
        "club_representative_id",
    )
    def _compute_target_display(self):
        """Store a normalized target label for list views and SQL-backed reports."""
        for rec in self:
            rec.target_display = rec._compliance_get_target_display(
                target_model=rec.target_model
            )

    @api.depends(
        "club_id",
        "player_id",
        "referee_id",
        "venue_id",
        "club_representative_id",
        "target_model",
    )
    def _compute_target_entity_label(self):
        """Return the display name of the resolved target entity for form-view display."""
        for rec in self:
            rec.target_entity_label = rec._compliance_get_target_display(
                target_model=rec.target_model
            )

    @api.constrains(
        "club_id",
        "player_id",
        "referee_id",
        "venue_id",
        "club_representative_id",
    )
    def _check_single_target(self):
        """Ensure exactly one target field is set."""
        for rec in self:
            target_fields = [
                rec.club_id,
                rec.player_id,
                rec.referee_id,
                rec.venue_id,
                rec.club_representative_id,
            ]
            set_count = sum(1 for f in target_fields if f)
            if set_count == 0:
                raise ValidationError("Exactly one target entity must be set.")
            if set_count > 1:
                raise ValidationError(
                    "Only one target entity can be set. Multiple targets found."
                )

    @api.constrains("requirement_id", "target_model")
    def _check_target_matches_requirement(self):
        """Ensure target matches requirement.target_model."""
        for rec in self:
            if not rec.requirement_id:
                continue
            expected_target = rec._compliance_get_target_record(
                target_model=rec.requirement_id.target_model,
            )
            if not expected_target:
                raise ValidationError(
                    f"Target entity does not match requirement model "
                    f"'{rec.requirement_id.target_model}'."
                )

    @api.constrains("issue_date", "expiry_date")
    def _check_dates(self):
        """Ensure expiry_date >= issue_date if both are set."""
        for rec in self:
            if rec.issue_date and rec.expiry_date:
                if rec.expiry_date < rec.issue_date:
                    raise ValidationError("Expiry date cannot be before issue date.")

    is_expired = fields.Boolean(
        string="Is Expired",
        compute="_compute_is_expired",
        search="_search_is_expired",
    )

    @api.depends("expiry_date")
    def _compute_is_expired(self):
        """Flag expired submissions so portal status logic can stay queryable."""
        today = fields.Date.context_today(self)
        for rec in self:
            rec.is_expired = bool(rec.expiry_date and rec.expiry_date < today)

    def _search_is_expired(self, operator, value):
        """Translate the boolean expiry filter into a date-domain safe for search()."""
        today = fields.Date.context_today(self)
        if (operator == "=" and value) or (operator == "!=" and not value):
            return [("expiry_date", "<", today), ("expiry_date", "!=", False)]
        return ["|", ("expiry_date", ">=", today), ("expiry_date", "=", False)]

    def _get_target_record(self):
        """Return the concrete target record bound to this submission."""
        self.ensure_one()
        return (
            self._compliance_get_target_record(target_model=self.target_model)
            or self._compliance_get_target_record()
        )

    def _portal_get_effective_status(self):
        """Collapse approved-plus-expired submissions into the portal expiry state."""
        self.ensure_one()
        if self.status == "approved" and self.is_expired:
            return "expired"
        return self.status

    @api.model
    def _portal_get_status_metadata(self, status_key, latest_submission=None):
        """Return the presentation contract used by portal compliance badges."""
        metadata = {
            "missing": {"label": "Missing", "tone": "danger"},
            "draft": {"label": "Draft", "tone": "secondary"},
            "submitted": {"label": "In Review", "tone": "warning"},
            "approved": {"label": "Approved", "tone": "success"},
            "rejected": {"label": "Rejected", "tone": "danger"},
            "replacement_requested": {
                "label": "Replacement Requested",
                "tone": "warning",
            },
            "expired": {"label": "Renewal Due", "tone": "danger"},
        }
        meta = dict(
            metadata.get(status_key, {"label": status_key, "tone": "secondary"})
        )
        if (
            status_key == "approved"
            and latest_submission
            and latest_submission.expiry_date
            and latest_submission.expiry_date
            <= fields.Date.context_today(self) + timedelta(days=30)
        ):
            meta = {"label": "Renewal Upcoming", "tone": "warning"}
        return meta

    def _recompute_related_checks(self):
        """Refresh compliance checks after a submission changes durable state."""
        Check = self.env["federation.compliance.check"]
        for record in self:
            target_record = record._get_target_record()
            if target_record and record.target_model:
                Check.recompute_checks_for_target(target_record, record.target_model)

    @api.model
    def _portal_prepare_submission_write_values(self, values=None):
        """Normalize portal-submitted fields before a draft is reused or created."""
        values = values or {}
        return {
            "issue_date": values.get("issue_date") or False,
            "expiry_date": values.get("expiry_date") or False,
            "notes": values.get("notes") or False,
        }

    @api.model
    def _portal_prepare_submission(
        self, requirement, target_record, values=None, user=None
    ):
        """Reuse or create the draft submission that a portal upload will submit.

        Access is re-checked through the elevated requirement service so stale
        portal links cannot create submissions for targets the caller no longer
        owns.
        """
        user = user or self.env.user
        PortalPrivilege = self.env["federation.portal.privilege"]
        Requirement = PortalPrivilege.elevate(
            self.env["federation.document.requirement"],
            user=user,
        )
        requirement = Requirement.browse(requirement.id)
        Requirement._portal_assert_target_access(requirement, target_record, user=user)

        latest_submission = requirement._portal_get_latest_submission(target_record)
        if latest_submission and latest_submission.status == "submitted":
            raise ValidationError(
                "A submission for this requirement is already awaiting review."
            )

        target_field_name = requirement._portal_get_target_field_name(
            requirement.target_model
        )
        if not target_field_name:
            raise ValidationError(
                "This requirement target cannot be handled through the portal."
            )

        prepared_values = self._portal_prepare_submission_write_values(values=values)

        if latest_submission and latest_submission.status in (
            "draft",
            "rejected",
            "replacement_requested",
        ):
            submission = PortalPrivilege.elevate(latest_submission, user=user)
        else:
            target_name = (
                target_record.display_name
                or getattr(target_record, "name", False)
                or requirement.name
            )
            submission = PortalPrivilege.portal_create(
                self,
                {
                    "name": f"{requirement.name} - {target_name}",
                    "requirement_id": requirement.id,
                    target_field_name: target_record.id,
                    "status": "draft",
                    **prepared_values,
                },
                user=user,
            )

        write_vals = {
            **prepared_values,
            "status": "draft",
            "reviewer_id": False,
            "reviewed_on": False,
        }
        PortalPrivilege.portal_write(submission, write_vals, user=user)
        return submission

    @api.model
    def _portal_create_submission_attachments(
        self, submission, uploaded_files=None, user=None
    ):
        """Create deduplicated attachments that satisfy the shared upload policy."""
        user = user or self.env.user
        PortalPrivilege = self.env["federation.portal.privilege"]
        AttachmentPolicy = self.env["federation.attachment.policy"]
        submission = PortalPrivilege.elevate(submission, user=user)
        submission.ensure_one()

        attachment_ids = []
        existing_attachment_ids = submission.attachment_ids.ids
        existing_checksums = set()
        for attachment in submission.attachment_ids:
            if not attachment.datas:
                continue
            existing_checksums.add(
                AttachmentPolicy.checksum_payload(base64.b64decode(attachment.datas))
            )

        Attachment = PortalPrivilege.elevate(self.env["ir.attachment"], user=user)
        for uploaded_file in uploaded_files or []:
            payload = uploaded_file.read()
            filename = getattr(uploaded_file, "filename", False)
            if not filename and not payload:
                continue
            upload = AttachmentPolicy.validate_upload(
                "portal_document",
                filename,
                payload,
                mimetype=getattr(uploaded_file, "mimetype", False),
            )
            if upload["checksum"] in existing_checksums:
                continue
            attachment = Attachment.create(
                {
                    "name": upload["filename"],
                    "datas": base64.b64encode(upload["payload"]),
                    "res_model": submission._name,
                    "res_id": submission.id,
                    "mimetype": upload["mimetype"],
                }
            )
            attachment_ids.append(attachment.id)
            existing_checksums.add(upload["checksum"])

        if attachment_ids:
            PortalPrivilege.portal_write(
                submission,
                {"attachment_ids": [(6, 0, existing_attachment_ids + attachment_ids)]},
                user=user,
            )
        return submission.attachment_ids

    @api.model
    def _portal_submit_submission(
        self,
        requirement,
        target_record,
        values=None,
        uploaded_files=None,
        user=None,
    ):
        """Execute the full portal submission flow as one validated service call.

        The draft is prepared first, attachments are policy-checked and
        deduplicated, and submission is blocked unless at least one attachment
        survives validation.
        """
        user = user or self.env.user
        submission = self._portal_prepare_submission(
            requirement,
            target_record,
            values=values,
            user=user,
        )
        self._portal_create_submission_attachments(
            submission,
            uploaded_files=uploaded_files,
            user=user,
        )
        if not submission.attachment_ids:
            raise ValidationError(
                "Upload at least one document attachment before submitting."
            )
        self.env["federation.portal.privilege"].portal_call(
            submission,
            "action_submit",
            user=user,
        )
        return submission

    @api.constrains("requirement_id", "expiry_date")
    def _check_expiry_date_required(self):
        """Ensure expiry_date is set when requirement requires it."""
        for rec in self:
            if rec.requirement_id and rec.requirement_id.requires_expiry_date:
                if not rec.expiry_date:
                    raise ValidationError(
                        f"Expiry date is required for requirement '{rec.requirement_id.name}'."
                    )

    def action_submit(self):
        """Submit the document for review."""
        for rec in self:
            if rec.status != "draft":
                raise ValidationError("Only draft documents can be submitted.")
            rec.write({"status": "submitted"})
            rec.flush_recordset()
        self._recompute_related_checks()

        Dispatcher = self.env.get("federation.notification.dispatcher")
        if Dispatcher is not None:
            for rec in self:
                Dispatcher.send_compliance_submission_received(rec)

    def action_approve(self):
        """Approve the submitted document."""
        for rec in self:
            if rec.status not in ("submitted", "replacement_requested"):
                raise ValidationError(
                    "Only submitted or replacement requested documents can be approved."
                )
            rec.write(
                {
                    "status": "approved",
                    "reviewer_id": self.env.user.id,
                    "reviewed_on": fields.Datetime.now(),
                }
            )
            rec.flush_recordset()
        self._recompute_related_checks()

    def action_reject(self):
        """Reject the submitted document."""
        for rec in self:
            if rec.status not in ("submitted", "replacement_requested"):
                raise ValidationError(
                    "Only submitted or replacement requested documents can be rejected."
                )
            rec.write(
                {
                    "status": "rejected",
                    "reviewer_id": self.env.user.id,
                    "reviewed_on": fields.Datetime.now(),
                }
            )
            rec.flush_recordset()
        self._recompute_related_checks()

        Dispatcher = self.env.get("federation.notification.dispatcher")
        if Dispatcher is not None:
            for rec in self:
                Dispatcher.send_compliance_remediation_requested(rec)

    def action_request_replacement(self):
        """Request a replacement document."""
        for rec in self:
            if rec.status != "approved":
                raise ValidationError(
                    "Only approved documents can have replacement requested."
                )
            rec.write(
                {
                    "status": "replacement_requested",
                    "reviewer_id": self.env.user.id,
                    "reviewed_on": fields.Datetime.now(),
                }
            )
            rec.flush_recordset()
        self._recompute_related_checks()

        Dispatcher = self.env.get("federation.notification.dispatcher")
        if Dispatcher is not None:
            for rec in self:
                Dispatcher.send_compliance_remediation_requested(rec)

    def action_reset_to_draft(self):
        """Reset to draft status."""
        for rec in self:
            rec.write({"status": "draft"})
            rec.flush_recordset()
        self._recompute_related_checks()
