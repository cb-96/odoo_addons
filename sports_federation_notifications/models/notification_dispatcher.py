from .notification_boundary import notification_effect

"""
Notification Dispatcher — event-driven notification routing.

Each method here maps to one row of the notification matrix in
``docs/reference/integration-contracts.md`` and resolves recipients before
delegating to ``send_email_template`` or ``create_activity``. Most modeled
workflow scenarios are live; suspension issuance uses a direct-email fallback
until a dedicated discipline template is introduced.

Usage (from any model override):
::

    Dispatcher = self.env.get("federation.notification.dispatcher")
    if Dispatcher is not None:
        Dispatcher.send_result_approved(self)
"""

from markupsafe import Markup, escape

from odoo import models


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

        return self.queue_direct_email(
            record,
            subject,
            body_html,
            ",".join(unique_emails),
            log_name=log_name,
        )

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

    @notification_effect()
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

    @notification_effect()
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

    @notification_effect()
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

    @notification_effect()
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

    @notification_effect()
    def send_result_submitted(self, match):
        """Handle send result submitted."""
        return self._create_group_activities(
            match,
            "sports_federation_result_control.group_result_validator",
            f"Verify result: {match.name}",
            note="A match result has been submitted and awaits verification.",
        )

    @notification_effect()
    def send_result_approved(self, match):
        """Notify recipients after the owning workflow authorized approval."""
        notification_match = match.sudo()
        emails = [
            notification_match.home_team_id.email,
            notification_match.home_team_id.club_id.email,
            notification_match.away_team_id.email,
            notification_match.away_team_id.club_id.email,
        ]
        return self._send_email_or_log(
            match,
            "sports_federation_notifications.template_federation_result_approved",
            f"Result approved: {match.name}",
            emails,
        )

    @notification_effect()
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

    @notification_effect()
    def send_referee_confirmation_overdue(self, match_officiating):
        """Handle send referee confirmation overdue."""
        return self._create_group_activities(
            match_officiating,
            "sports_federation_base.group_federation_manager",
            f"Referee confirmation overdue: {match_officiating.match_id.name}",
            note=match_officiating.readiness_feedback
            or "Referee confirmation deadline has been missed.",
        )

    @notification_effect()
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

    @notification_effect()
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

    @notification_effect()
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

    @notification_effect()
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

    @notification_effect()
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

    @notification_effect()
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

    @notification_effect()
    def send_suspension_issued(self, suspension):
        """Notify the player and club contact when a suspension is issued.

        Every value comes from records that clubs or staff typed (player and
        case names, notes), so the body is built with ``Markup`` and each value
        is escaped. Text is translated in the player's language when set.
        """
        player = suspension.player_id
        club = player.club_id
        emails = [player.email, club.email]
        lang = player.lang or self.env.lang
        env = self.with_context(lang=lang).env
        no_notes = env._("No additional notes provided.")
        lines = [
            (env._("Case"), suspension.case_id.display_name or ""),
            (env._("Start date"), suspension.date_start or ""),
            (env._("End date"), suspension.date_end or ""),
            (env._("Notes"), suspension.notes or no_notes),
        ]
        body_html = (
            Markup("<p>%s</p>") % env._("Dear federation contact,")
            + Markup("<p>%s</p>")
            # Translations are text, not markup: escape them, then fill in.
            % Markup(escape(env._("A suspension has been activated for %s.")))
            % (Markup("<strong>%s</strong>") % (player.display_name or ""))
            + Markup("").join(
                Markup("<p>%s: %s</p>") % (label, value) for label, value in lines
            )
            + Markup("<p>%s<br/>%s</p>")
            % (env._("Best regards,"), env._("Sports Federation"))
        )
        subject = env._("Suspension issued: %s", suspension.name)
        return self._send_direct_email_or_log(
            suspension,
            subject,
            body_html,
            # Internal log name: stable English text for operators and search.
            f"Suspension issued: {suspension.name}",
            emails,
        )
