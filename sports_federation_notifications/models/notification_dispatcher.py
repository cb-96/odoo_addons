"""
Notification Dispatcher — event-driven notification routing.

Each method here maps to one row in ``odoo/NOTIFICATION_MATRIX.md`` and
resolves recipients before delegating to ``send_email_template`` or
``create_activity``. Most modeled workflow scenarios are now live; suspension
issuance uses a direct-email fallback until a dedicated discipline template is
introduced.

Usage (from any model override):
::

    Dispatcher = self.env.get("federation.notification.dispatcher")
    if Dispatcher is not None:
        Dispatcher.send_result_approved(self)
"""

from odoo import fields, models
from odoo.addons.sports_federation_base.models.failure_feedback import (
    build_failure_feedback,
)


class FederationNotificationDispatcher(models.AbstractModel):
    """Dispatcher for domain-event driven notifications.

    Inherits the notification service helpers (``send_email_template``,
    ``create_activity``) and adds domain-specific dispatch methods.
    """

    _name = "federation.notification.dispatcher"
    _description = "Federation Notification Dispatcher"
    _inherit = "federation.notification.service"

    def _unique_emails(self, emails):
        """Handle unique emails."""
        unique = []
        for email in emails:
            normalized = (email or "").strip()
            if normalized and normalized not in unique:
                unique.append(normalized)
        return unique

    def _log_missing_recipients(self, record, log_name, notification_type, message):
        """Handle log missing recipients."""
        return (
            self.env["federation.notification.log"]
            .sudo()
            .create(
                {
                    "name": log_name,
                    "target_model": record._name,
                    "target_res_id": record.id,
                    "notification_type": notification_type,
                    "state": "failed",
                    "failure_category": "configuration_error",
                    "operator_message": message,
                }
            )
        )

    def _send_email_or_log(self, record, template_xmlid, log_name, emails):
        """Handle send email or log."""
        unique_emails = self._unique_emails(emails)
        if not unique_emails:
            return self._log_missing_recipients(
                record,
                log_name,
                "email",
                "No recipient email available for this notification.",
            )
        return self.send_email_template(
            record,
            template_xmlid,
            email_to=unique_emails,
            log_name=log_name,
        )

    def _send_direct_email_or_log(self, record, subject, body_html, log_name, emails):
        """Send a direct email when a dedicated template does not exist."""
        unique_emails = self._unique_emails(emails)
        if not unique_emails:
            return self._log_missing_recipients(
                record,
                log_name,
                "email",
                "No recipient email available for this notification.",
            )

        log = (
            self.env["federation.notification.log"]
            .sudo()
            .create(
                {
                    "name": log_name,
                    "target_model": record._name,
                    "target_res_id": record.id,
                    "recipient_email": ",".join(unique_emails),
                    "notification_type": "email",
                    "state": "pending",
                }
            )
        )
        email_from = (
            self.env.user.company_id.email_formatted
            or self.env.user.email_formatted
            or self.env.company.email
            or self.env.user.email
            or False
        )

        try:
            mail = (
                self.env["mail.mail"]
                .sudo()
                .create(
                    {
                        "subject": subject,
                        "body_html": body_html,
                        "email_to": ",".join(unique_emails),
                        "email_from": email_from,
                        "auto_delete": False,
                    }
                )
            )
            mail.send()
            log.write(
                {
                    "state": "sent",
                    "sent_on": fields.Datetime.now(),
                    "failure_category": False,
                    "operator_message": False,
                }
            )
        except Exception as exc:
            failure_category, operator_message = build_failure_feedback(error=exc)
            log.write(
                {
                    "state": "failed",
                    "failure_category": failure_category,
                    "operator_message": operator_message,
                    "message": False,
                }
            )

        return log

    def _create_group_activities(self, record, group_xmlid, summary, note=None):
        """Handle create group activities."""
        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        users = group.user_ids if group else self.env["res.users"].browse([])
        if not users:
            return self._log_missing_recipients(
                record,
                summary,
                "activity",
                f"No users configured in group {group_xmlid}.",
            )

        logs = self.env["federation.notification.log"].sudo()
        for user in users:
            logs |= self.create_activity(record, user.id, summary, note=note)
        return logs

    # ------------------------------------------------------------------
    # Season registration events
    # ------------------------------------------------------------------

    def _get_season_registration_recipient(self, registration):
        """Return season registration recipient."""
        partner = False
        if (
            "partner_id" in registration._fields
            and registration.partner_id
            and registration.partner_id.email
        ):
            partner = registration.partner_id

        email_to = False
        if not partner:
            email_to = registration.club_id.email or False

        return partner, email_to

    def send_season_registration_confirmed(self, registration):
        """Handle send season registration confirmed."""
        partner, email_to = self._get_season_registration_recipient(registration)
        return self.send_email_template(
            registration,
            "sports_federation_notifications.template_federation_season_registration_confirmed",
            partner=partner,
            email_to=email_to,
            log_name=f"Season registration confirmed: {registration.name}",
        )

    def send_season_registration_rejected(self, registration):
        """Handle send season registration rejected."""
        partner, email_to = self._get_season_registration_recipient(registration)
        return self.send_email_template(
            registration,
            "sports_federation_notifications.template_federation_season_registration_rejected",
            partner=partner,
            email_to=email_to,
            log_name=f"Season registration rejected: {registration.name}",
        )

    # ------------------------------------------------------------------
    # Tournament events
    # ------------------------------------------------------------------

    def send_tournament_published(self, tournament):
        """Handle send tournament published."""
        emails = tournament.participant_ids.mapped(
            "club_id.email"
        ) + tournament.participant_ids.mapped("team_id.email")
        return self._send_email_or_log(
            tournament,
            "sports_federation_notifications.template_federation_tournament_published",
            f"Tournament published: {tournament.name}",
            emails,
        )

    # ------------------------------------------------------------------
    # Participant events
    # ------------------------------------------------------------------

    def send_participant_confirmed(self, participant):
        """Handle send participant confirmed."""
        emails = [participant.team_id.email, participant.club_id.email]
        return self._send_email_or_log(
            participant,
            "sports_federation_notifications.template_federation_participant_confirmed",
            f"Participant confirmed: {participant.name}",
            emails,
        )

    # ------------------------------------------------------------------
    # Match result events
    # ------------------------------------------------------------------

    def send_result_submitted(self, match):
        """Handle send result submitted."""
        return self._create_group_activities(
            match,
            "sports_federation_result_control.group_result_validator",
            f"Verify result: {match.name}",
            note="A match result has been submitted and awaits verification.",
        )

    def send_result_approved(self, match):
        """Handle send result approved."""
        emails = [
            match.home_team_id.email,
            match.home_team_id.club_id.email,
            match.away_team_id.email,
            match.away_team_id.club_id.email,
        ]
        return self._send_email_or_log(
            match,
            "sports_federation_notifications.template_federation_result_approved",
            f"Result approved: {match.name}",
            emails,
        )

    def send_result_contested(self, match):
        """Handle send result contested."""
        manager_group = self.env.ref(
            "sports_federation_base.group_federation_manager",
            raise_if_not_found=False,
        )
        manager_emails = manager_group.user_ids.mapped("email") if manager_group else []
        emails = [
            match.home_team_id.email,
            match.home_team_id.club_id.email,
            match.away_team_id.email,
            match.away_team_id.club_id.email,
            *manager_emails,
        ]
        return self._send_email_or_log(
            match,
            "sports_federation_notifications.template_federation_result_contested",
            f"Result contested: {match.name}",
            emails,
        )

    # ------------------------------------------------------------------
    # Officiating events
    # ------------------------------------------------------------------

    def send_referee_confirmation_overdue(self, match_officiating):
        """Handle send referee confirmation overdue."""
        return self._create_group_activities(
            match_officiating,
            "sports_federation_base.group_federation_manager",
            f"Referee confirmation overdue: {match_officiating.match_id.name}",
            note=match_officiating.readiness_feedback
            or "Referee confirmation deadline has been missed.",
        )

    def send_referee_shortage_alert(self, match):
        """Handle send referee shortage alert."""
        return self._create_group_activities(
            match,
            "sports_federation_base.group_federation_manager",
            f"Referee shortage: {match.name}",
            note=getattr(match, "official_readiness_issues", False)
            or "Match is missing required officials.",
        )

    # ------------------------------------------------------------------
    # Standings events
    # ------------------------------------------------------------------

    def send_standing_frozen(self, standing):
        """Handle send standing frozen."""
        emails = standing.tournament_id.participant_ids.mapped("club_id.email")
        return self._send_email_or_log(
            standing,
            "sports_federation_notifications.template_federation_standing_frozen",
            f"Standing frozen: {standing.name}",
            emails,
        )

    # ------------------------------------------------------------------
    # Finance events
    # ------------------------------------------------------------------

    def send_finance_event_confirmed(self, finance_event):
        """Handle send finance event confirmed."""
        emails = [
            finance_event.partner_id.email,
            finance_event.club_id.email,
            finance_event.player_id.email,
            finance_event.referee_id.email,
        ]
        return self._send_email_or_log(
            finance_event,
            "sports_federation_notifications.template_federation_finance_confirmed",
            f"Finance event confirmed: {finance_event.name}",
            emails,
        )

    # ------------------------------------------------------------------
    # Compliance events
    # ------------------------------------------------------------------

    def send_compliance_submission_received(self, submission):
        """Handle send compliance submission received."""
        return self._create_group_activities(
            submission,
            "sports_federation_base.group_federation_manager",
            f"Review compliance submission: {submission.name}",
            note=(
                f"Requirement: {submission.requirement_id.name}<br/>"
                f"Target: {submission.target_display or 'Unknown'}"
            ),
        )

    def send_compliance_remediation_requested(self, submission):
        """Handle send compliance remediation requested."""
        return self._create_group_activities(
            submission,
            "sports_federation_base.group_federation_manager",
            f"Compliance remediation follow-up: {submission.name}",
            note=(
                f"Requirement: {submission.requirement_id.name}<br/>"
                f"Target: {submission.target_display or 'Unknown'}<br/>"
                f"Status: {submission.status}"
            ),
        )

    # ------------------------------------------------------------------
    # Officiating events
    # ------------------------------------------------------------------

    def send_referee_assigned(self, match_officiating):
        """Handle send referee assigned."""
        return self._send_email_or_log(
            match_officiating,
            "sports_federation_notifications.template_federation_referee_assigned",
            f"Referee assigned: {match_officiating.match_id.name}",
            [match_officiating.referee_id.email],
        )

    # ------------------------------------------------------------------
    # Discipline events
    # ------------------------------------------------------------------

    def send_suspension_issued(self, suspension):
        """Notify the player and club contact when a suspension is issued."""
        player = suspension.player_id
        club = player.club_id
        emails = [player.email, club.email]
        subject = f"Suspension issued: {suspension.name}"
        body_html = (
            "<p>Dear federation contact,</p>"
            f"<p>A suspension has been activated for <strong>{player.display_name}</strong>.</p>"
            f"<p>Case: {suspension.case_id.display_name}</p>"
            f"<p>Start date: {suspension.date_start}</p>"
            f"<p>End date: {suspension.date_end}</p>"
            f"<p>Notes: {suspension.notes or 'No additional notes provided.'}</p>"
            "<p>Best regards,<br/>Sports Federation</p>"
        )
        return self._send_direct_email_or_log(
            suspension,
            subject,
            body_html,
            f"Suspension issued: {suspension.name}",
            emails,
        )
