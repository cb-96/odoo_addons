"""Ask clubs for officials as soon as a schedule is published.

Club referee duties were only created by the "Assign Officials" wizard, so a
published match day had no "Official needed" work for any club until staff
remembered to run it. Publication now creates the duties itself, using the same
allocation as the wizard (fair load per club, clubs playing at the same time
avoided, never the club's own opponent).

The rule set of a match says how many officials it needs (``Referees required
per match``); 0 means no requirement, so nothing is created. A rule set can opt
out with ``Ask clubs for officials on publication``. Publication must never be
blocked by officiating: a problem is logged and noted on the match day, and
staff can still run the wizard.
"""

import logging

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)

# The wizard asks for the first N roles of this list for N officials per match.
ROLE_ORDER = ("head", "assistant_1", "assistant_2", "fourth", "table")


class FederationScheduleApprovalCommandsOfficials(models.AbstractModel):
    _inherit = "federation.schedule.approval.commands"

    @api.model
    def publish(self, schedule_id, reason=False, expected_publication_id=None):
        publication = super().publish(
            schedule_id, reason=reason, expected_publication_id=expected_publication_id
        )
        self._ensure_club_duties(
            self.env["federation.match"]
            .sudo()
            .search([("schedule_publication_id", "=", publication.id)])
        )
        return publication

    @api.model
    def link_placeholder_matches(self, matches):
        result = super().link_placeholder_matches(matches)
        self._ensure_club_duties(matches.sudo().filtered("schedule_publication_id"))
        return result

    @api.model
    def _club_duty_roles(self, match):
        """Roles the clubs have to supply for a match, or none."""
        rule_set = match._get_effective_officiating_rule_set()
        if not rule_set or not rule_set.club_duties_on_publication:
            return 0
        return min(max(rule_set.referee_required_count or 0, 0), len(ROLE_ORDER))

    @api.model
    def _ensure_club_duties(self, matches):
        """Create the open club duties of published matches that still need them."""
        matches = matches.sudo().filtered(
            lambda match: match.logical_fixture_id
            and match.schedule_publication_id
            and match.state != "cancelled"
        )
        by_count = {}
        for match in matches:
            count = self._club_duty_roles(match)
            if count:
                by_count.setdefault(count, self.env["federation.match"])
                by_count[count] |= match
        created = self.env["federation.match.club.referee.duty"]
        for count, group in by_count.items():
            try:
                with self.env.cr.savepoint():
                    created |= self._create_club_duties(group, count)
            except (AccessError, UserError, ValidationError) as error:
                self._report_duty_problem(group, error)
        return created

    @api.model
    def _create_club_duties(self, matches, officials_per_match):
        # The wizard owns the allocation rules; an in-memory (unsaved) wizard
        # lets publication reuse them without leaving a record behind.
        wizard = (
            self.env["federation.matchday.assign.official.wizard"]
            .sudo()
            .new(
                {
                    "assignment_type": "auto_club",
                    "officials_per_match": officials_per_match,
                    "open_duties": True,
                    "avoid_clubs_playing_same_slot": True,
                    "allow_playing_club_fallback": True,
                    "preserve_existing_assignments": True,
                }
            )
        )
        return wizard._auto_assign_club_duties(matches)

    @api.model
    def _report_duty_problem(self, matches, error):
        _logger.warning("Club duties not created on publication: %s", error)
        for matchday in matches.mapped("schedule_publication_id.matchday_id"):
            matchday.message_post(
                body=_(
                    "Club duties could not be created automatically: %(error)s "
                    "Use Assign Officials on this match day to create them.",
                    error=str(error),
                )
            )
