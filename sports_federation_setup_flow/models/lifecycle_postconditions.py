from odoo import _, api, models
from odoo.exceptions import ValidationError
from ..lifecycle_handoffs import HANDOFFS


class FederationLifecyclePostconditions(models.AbstractModel):
    """Validate cross-addon state after approved lifecycle handoffs."""

    _name = "federation.lifecycle.postconditions"
    _description = "Competition Lifecycle Postconditions"

    @api.model
    def enforce(self, handoff, records):
        if handoff not in HANDOFFS:
            raise ValueError("Unknown lifecycle handoff %s" % handoff)
        violations = getattr(self, "_check_%s" % handoff)(records.sudo().exists())
        if violations:
            raise ValidationError(
                _("The lifecycle handoff is incomplete:\n- %s")
                % "\n- ".join(violations)
            )
        return True

    def _check_registration_finalized(self, windows):
        result = []
        for window in windows:
            pset = window.participant_set_id
            if window.state != "finalized" or not pset or pset.state != "finalized":
                result.append(
                    _("Registration is not finalized with a finalized team list.")
                )
                continue
            confirmed = (
                self.env["federation.tournament.participant"]
                .search(
                    [
                        ("tournament_id", "=", window.division_id.id),
                        ("state", "=", "confirmed"),
                    ]
                )
                .mapped("team_id")
            )
            if pset.line_ids.mapped("team_id") - confirmed:
                result.append(
                    _("Finalized teams are missing from division participants.")
                )
        return result

    def _check_format_frozen(self, structures):
        return [
            _("A confirmed format has no generated matches.")
            for item in structures
            if item.state == "frozen" and not item.fixture_ids
        ]

    def _check_schedule_generated(self, schedules):
        result = []
        for schedule in schedules:
            for assignment in schedule.assignment_ids:
                if assignment.slot_id.matchday_id != schedule.matchday_id:
                    result.append(_("A match is planned on another game day."))
                if assignment.fixture_id.edition_id != schedule.edition_id:
                    result.append(_("A planned match belongs to another competition."))
        return result

    def _check_schedule_published(self, publications):
        result = []
        for publication in publications:
            schedule, day = publication.schedule_id, publication.matchday_id
            if publication.state != "live" or day.current_publication_id != publication:
                result.append(
                    _("The new publication is not the game day's live schedule.")
                )
            for assignment in schedule.assignment_ids:
                match = assignment.fixture_id.operational_match_id
                if not match:
                    continue
                if (
                    match.schedule_publication_id != publication
                    or match.published_slot_id != assignment.slot_id
                    or not match.date_scheduled
                ):
                    result.append(
                        _(
                            "A published match is missing its publication, slot or kickoff."
                        )
                    )
                if "venue_id" in match._fields and not match.venue_id:
                    result.append(_("A published match has no venue."))
                if (
                    "playing_area_id" in match._fields
                    and assignment.slot_id.court_id
                    and not match.playing_area_id
                ):
                    result.append(_("A published match has no playing area."))
        return result

    def _check_matchday_opened(self, days):
        return [
            _("A game day command completed without opening the game day.")
            for day in days
            if day.state != "open"
        ]

    def _check_matchday_closed(self, days):
        return [
            _("A game day command completed without closing the game day.")
            for day in days
            if day.state != "closed"
        ]

    def _check_competition_finished(self, editions):
        result = []
        for edition in editions:
            if edition.state != "closed":
                result.append(_("The competition is not closed."))
            if self.env["federation.matchday"].search_count(
                [
                    ("edition_id", "=", edition.id),
                    ("state", "not in", ("closed", "cancelled")),
                ]
            ):
                result.append(_("Game days are still open."))
        return result

    def _check_competition_archived(self, editions):
        Task = self.env.get("federation.operation.task")
        if Task is None:
            return []
        result = []
        for edition in editions:
            if Task.search_count(
                [
                    (
                        "tournament_id",
                        "in",
                        edition.with_context(active_test=False).tournament_ids.ids,
                    ),
                    ("state", "!=", "done"),
                ]
            ):
                result.append(_("Archived competition work is still open."))
        return result
