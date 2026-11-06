from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MatchdayCommunication(models.Model):
    _inherit = "federation.matchday"
    communication_revision = fields.Integer(default=0, copy=False, readonly=True)

    def write(self, vals):
        occurred_on = fields.Datetime.now()
        watched = {"venue_id", "current_publication_id"} & vals.keys()
        before = (
            {
                record.id: (record.venue_id.id, record.current_publication_id.id)
                for record in self
            }
            if watched
            else {}
        )
        result = super().write(vals)
        def notify():
            service = self.env['federation.notification.service']
            for day in self if watched else self.browse():
                after = (day.venue_id.id, day.current_publication_id.id)
                if before[day.id] == after or not day.current_publication_id or day.current_publication_id.state != 'live':
                    continue
                # Publishing a new immutable snapshot is the authoritative schedule-change boundary.
                revision = day.communication_revision + 1
                super(MatchdayCommunication, day).write({'communication_revision': revision})
                service._publish_action(day, 'schedule_change', 'schedule:%s:%s' % (day.id, revision),
                                        service._day_routes(day), urgent=True, occurred_on=occurred_on)
        self.env["federation.notification.service"]._run_notification_effect(
            notify, source=self, name="MatchdayCommunication",
        )
        return result


class OfficialResponseCommunication(models.Model):
    _inherit = "federation.match.referee"
    communication_revision = fields.Integer(default=0, copy=False, readonly=True)

    def write(self, vals):
        occurred_on = fields.Datetime.now()
        before = {record.id: record.state for record in self} if "state" in vals else {}
        result = super().write(vals)
        def notify():
            for assignment in self if before else self.browse():
                if assignment.state != 'cancelled' or before[assignment.id] == 'cancelled':
                    continue
                revision = assignment.communication_revision + 1
                super(OfficialResponseCommunication, assignment).write({'communication_revision': revision})
                service = self.env['federation.notification.service']
                edition = assignment.match_id._competition_workflow_edition()
                service._publish_action(assignment, 'official_response', 'coverage:%s:%s' % (assignment.id, revision),
                                        service._organiser_routes(edition), urgent=True, occurred_on=occurred_on)
        self.env["federation.notification.service"]._run_notification_effect(
            notify, source=self, name="OfficialResponseCommunication",
        )
        return result


class DocumentReturnCommunication(models.Model):
    _inherit = "federation.player.parental.approval"
    replaces_approval_id = fields.Many2one(
        "federation.player.parental.approval",
        ondelete="restrict",
        copy=False,
        index=True,
    )
    replacement_ids = fields.One2many(
        "federation.player.parental.approval", "replaces_approval_id"
    )

    @api.constrains("replaces_approval_id", "player_id")
    def _check_replacement_player(self):
        for document in self:
            if document.replaces_approval_id and (
                document.replaces_approval_id == document
                or document.replaces_approval_id.player_id != document.player_id
            ):
                raise ValidationError(
                    _(
                        "A replacement must refer to earlier evidence for the same player."
                    )
                )

    @api.model
    def _portal_create_parental_approval(self, player, values, upload, user=None):
        document = super()._portal_create_parental_approval(
            player, values, upload, user=user
        )
        returned = self.sudo().search(
            [
                ("player_id", "=", player.id),
                ("state", "=", "replacement_requested"),
                ("id", "!=", document.id),
            ],
            order="id desc",
            limit=1,
        )
        if returned:
            document.sudo().write({"replaces_approval_id": returned.id})
        return document

    communication_revision = fields.Integer(default=0, copy=False, readonly=True)

    def write(self, vals):
        occurred_on = fields.Datetime.now()
        before = {record.id: record.state for record in self} if "state" in vals else {}
        result = super().write(vals)
        def notify():
            for document in self if before else self.browse():
                if document.state != 'replacement_requested' or before[document.id] == 'replacement_requested':
                    continue
                revision = document.communication_revision + 1
                super(DocumentReturnCommunication, document).write({'communication_revision': revision})
                service = self.env['federation.notification.service']
                routes = [(document.submitted_by_id.id, 'submitter')] if document.submitted_by_id else []
                reps = self.env['federation.club.representative'].sudo().search([
                    ('is_current', '=', True), ('club_id', '=', document.player_id.club_id.id)])
                routes += [(rep.effective_user_id.id or rep.user_id.id, 'club') for rep in reps]
                service._publish_action(document, 'document_returned', 'document:%s:%s' % (document.id, revision), routes, occurred_on=occurred_on)
        self.env["federation.notification.service"]._run_notification_effect(
            notify, source=self, name="DocumentReturnCommunication",
        )
        return result


class CommunicationLogRecovery(models.Model):
    _inherit = "federation.notification.log"

    def action_queue_retry(self):
        linked = (
            self.env["federation.communication.delivery"]
            .sudo()
            .search([("log_id", "in", self.ids)])
        )
        if linked:
            linked.with_user(self.env.user).action_retry_delivery()
        legacy = self - linked.mapped("log_id")
        return (
            super(CommunicationLogRecovery, legacy).action_queue_retry()
            if legacy
            else True
        )


class CommunicationTaskDigest(models.Model):
    _inherit = "federation.operation.task"

    def cron_send_action_digests(self):
        # Existing scheduled actions share the new digest identity instead of adding activities.
        return self.env["federation.notification.service"]._cron_action_digests()
