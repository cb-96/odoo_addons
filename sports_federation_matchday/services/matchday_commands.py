from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class FederationMatchdayCommands(models.AbstractModel):
    _name = "federation.matchday.commands"
    _description = "Match-Day Operations Commands"

    def _resolve(self, matchday_id):
        matchday = self.env["federation.matchday"].browse(int(matchday_id)).exists()
        if not matchday:
            raise ValidationError(_("The match day no longer exists."))
        self.env["federation.competition.role.assignment"].assert_role(
            matchday.edition_id, "matchday_manager", "competition_director"
        )
        return matchday

    def _require_open(self, matchday):
        if matchday.state != "open" or not matchday.active_session_id:
            raise ValidationError(
                _("Open the published match day before performing live operations.")
            )

    @api.model
    def open_matchday(self, matchday_id):
        with self.env.cr.savepoint():
            return self._open_matchday(matchday_id)

    @api.model
    def _open_matchday(self, matchday_id):
        matchday = self._resolve(matchday_id)
        publication = matchday.current_publication_id
        if (
            matchday.state != "scheduled"
            or not publication
            or publication.state != "live"
        ):
            raise ValidationError(
                _("Only the current live published match day can be opened.")
            )
        if publication.snapshot_digest != self.env[
            "federation.schedule.publication"
        ].digest_snapshot(publication.assignment_snapshot):
            raise ValidationError(
                _("The published schedule snapshot failed its integrity check.")
            )
        session = (
            self.env["federation.matchday.session"]
            .sudo()
            .create(
                {
                    "matchday_id": matchday.id,
                    "publication_id": publication.id,
                    "publication_digest": publication.snapshot_digest,
                }
            )
        )
        for court in matchday.slot_ids.mapped("court_id"):
            self.env["federation.matchday.court.status"].sudo().create(
                {"matchday_id": matchday.id, "court_id": court.id}
            )
        transition = self.env["federation.workflow.transition"]
        result = transition.execute(
            matchday.sudo(),
            "open",
            {"scheduled"},
            event_type="matchday_opened",
            description=_("Published match day opened for live operations."),
        )
        transition.execute(
            session,
            "open",
            {"open"},
            event_type="matchday_session_opened",
            description=_("Match-day execution session opened."),
        )
        self.env["federation.competition.event"].emit(
            matchday,
            "matchday_opened",
            {"session_id": session.id, "publication_id": publication.id},
        )
        result.update({"session_id": session.id, "publication_id": publication.id})
        return result

    @api.model
    def report_incident(self, matchday_id, incident_type, description):
        with self.env.cr.savepoint():
            return self._report_incident(matchday_id, incident_type, description)

    @api.model
    def _report_incident(self, matchday_id, incident_type, description):
        matchday = self._resolve(matchday_id)
        self._require_open(matchday)
        incident = (
            self.env["federation.matchday.incident"]
            .sudo()
            .create(
                {
                    "matchday_id": matchday.id,
                    "incident_type": incident_type,
                    "description": description,
                }
            )
        )
        self.env["federation.audit.event"].log_record_events(
            event_family="workflow_transition",
            event_type="matchday_incident_reported",
            description=_("Match-day incident reported."),
            records=incident,
            actor=self.env.user,
            action_name="report_incident",
            changed_fields=("incident_type", "description"),
        )
        return {
            "record_model": incident._name,
            "record_ids": incident.ids,
            "current_state": "unresolved",
            "actor_id": self.env.user.id,
            "incident_id": incident.id,
        }

    @api.model
    def set_court_status(
        self, matchday_id, court_id, state, delay_minutes=0, note=False
    ):
        with self.env.cr.savepoint():
            return self._set_court_status(
                matchday_id, court_id, state, delay_minutes, note
            )

    @api.model
    def _set_court_status(
        self, matchday_id, court_id, state, delay_minutes=0, note=False
    ):
        matchday = self._resolve(matchday_id)
        self._require_open(matchday)
        status = self.env["federation.matchday.court.status"].search(
            [("matchday_id", "=", matchday.id), ("court_id", "=", int(court_id))],
            limit=1,
        )
        if not status:
            raise ValidationError(_("The court is outside this match day."))
        if state not in ("available", "delayed", "unavailable"):
            raise ValidationError(_("Invalid court status."))
        result = self.env["federation.workflow.transition"].execute(
            status.sudo(),
            state,
            {"available", "delayed", "unavailable"},
            values={
                "delay_minutes": max(0, int(delay_minutes or 0)),
                "note": note,
            },
            reason=note,
            event_type="matchday_court_status_changed",
            description=_("Match-day court status changed."),
        )
        if state != "available":
            self.report_incident(
                matchday.id,
                "court_unavailable" if state == "unavailable" else "delay",
                note or _("Court status changed."),
            )
        result["court_status_id"] = status.id
        return result

    @api.model
    def resolve_incident(self, incident_id):
        with self.env.cr.savepoint():
            return self._resolve_incident(incident_id)

    @api.model
    def _resolve_incident(self, incident_id):
        incident = (
            self.env["federation.matchday.incident"].browse(int(incident_id)).exists()
        )
        matchday = self._resolve(incident.matchday_id.id)
        self._require_open(matchday)
        result = self.env["federation.workflow.transition"].execute(
            incident.sudo(),
            True,
            {False},
            state_field="resolved",
            values={
                "resolved_at": fields.Datetime.now(),
                "resolved_by_id": self.env.user.id,
            },
            event_type="matchday_incident_resolved",
            description=_("Match-day incident resolved."),
        )
        result["incident_id"] = incident.id
        return result

    @api.model
    def record_schedule_deviation(
        self,
        matchday_id,
        match_id,
        deviation_type,
        reason,
        new_slot_id=False,
        delay_minutes=0,
    ):
        with self.env.cr.savepoint():
            return self._record_schedule_deviation(
                matchday_id,
                match_id,
                deviation_type,
                reason,
                new_slot_id,
                delay_minutes,
            )

    @api.model
    def _record_schedule_deviation(
        self,
        matchday_id,
        match_id,
        deviation_type,
        reason,
        new_slot_id=False,
        delay_minutes=0,
    ):
        matchday = self._resolve(matchday_id)
        self._require_open(matchday)
        if not (reason or "").strip():
            raise ValidationError(_("Explain the operational schedule change."))
        if deviation_type not in ("move", "delay", "postpone", "cancel"):
            raise ValidationError(_("Invalid operational deviation type."))
        match = self.env["federation.match"].browse(int(match_id)).exists()
        if (
            not match
            or match.schedule_publication_id != matchday.current_publication_id
        ):
            raise ValidationError(
                _("The match is not part of the publication opened for this match day.")
            )
        old_slot = match.operational_slot_id or match.published_slot_id
        new_slot = self.env["federation.schedule.slot"]
        values = {}
        if deviation_type == "move":
            new_slot = (
                self.env["federation.schedule.slot"]
                .browse(int(new_slot_id or 0))
                .exists()
            )
            if (
                not new_slot
                or new_slot.matchday_id != matchday
                or new_slot.state != "available"
            ):
                raise ValidationError(_("Select an available slot on this match day."))
            occupied = self.env["federation.match"].search(
                [
                    ("operational_slot_id", "=", new_slot.id),
                    ("id", "!=", match.id),
                    ("operational_status", "not in", ("postponed", "cancelled")),
                ],
                limit=1,
            )
            if occupied:
                raise ValidationError(
                    _("The selected operational slot is already occupied.")
                )
            values = {
                "operational_slot_id": new_slot.id,
                "operational_status": "moved",
                "date_scheduled": new_slot.start_datetime,
            }
        elif deviation_type == "delay":
            minutes = int(delay_minutes or 0)
            if minutes <= 0:
                raise ValidationError(
                    _("The delay must be a positive number of minutes.")
                )
            base = match.date_scheduled or old_slot.start_datetime
            values = {
                "operational_slot_id": old_slot.id,
                "operational_status": "delayed",
                "date_scheduled": base + timedelta(minutes=minutes),
            }
        elif deviation_type == "postpone":
            values = {
                "operational_slot_id": False,
                "operational_status": "postponed",
                "date_scheduled": False,
            }
        else:
            values = {
                "operational_slot_id": False,
                "operational_status": "cancelled",
                "date_scheduled": False,
                "state": "cancelled",
            }
        operational_status = values.pop("operational_status")
        result = self.env["federation.workflow.transition"].execute(
            match.sudo(),
            operational_status,
            {"as_published", "moved", "delayed", "postponed", "cancelled"},
            values=values,
            state_field="operational_status",
            reason=reason,
            reason_required=True,
            event_type="matchday_match_deviated",
            description=_("Operational match schedule changed."),
        )
        deviation = (
            self.env["federation.matchday.deviation"]
            .sudo()
            .create(
                {
                    "matchday_id": matchday.id,
                    "session_id": matchday.active_session_id.id,
                    "publication_id": matchday.current_publication_id.id,
                    "match_id": match.id,
                    "deviation_type": deviation_type,
                    "old_slot_id": old_slot.id if old_slot else False,
                    "new_slot_id": new_slot.id if new_slot else False,
                    "delay_minutes": int(delay_minutes or 0),
                    "reason": reason,
                    "actor_id": self.env.user.id,
                }
            )
        )
        incident = self.env["federation.matchday.incident"].sudo().create(
            {
                "matchday_id": matchday.id,
                "incident_type": "schedule_change",
                "description": _(
                    "%(kind)s for %(match)s: %(reason)s",
                    kind=deviation_type.title(),
                    match=match.display_name,
                    reason=reason,
                ),
            }
        )
        self.env["federation.competition.event"].emit(
            matchday,
            "matchday_schedule_deviation_recorded",
            {
                "deviation_id": deviation.id,
                "match_id": match.id,
                "type": deviation_type,
                "old_slot_id": old_slot.id if old_slot else False,
                "new_slot_id": new_slot.id if new_slot else False,
            },
        )
        result.update(
            {
                "deviation_id": deviation.id,
                "match_id": match.id,
                "incident_id": incident.id,
            }
        )
        return result

    @api.model
    def close_matchday(self, matchday_id, close_note=False, force=False):
        with self.env.cr.savepoint():
            return self._close_matchday(matchday_id, close_note, force)

    @api.model
    def _close_matchday(self, matchday_id, close_note=False, force=False):
        matchday = self._resolve(matchday_id)
        self._require_open(matchday)
        unresolved = self.env["federation.matchday.incident"].search(
            [("matchday_id", "=", matchday.id), ("resolved", "=", False)]
        )
        scheduled_matches = self.env["federation.match"].search(
            [("schedule_publication_id", "=", matchday.current_publication_id.id)]
        )
        unfinished = scheduled_matches.filtered(
            lambda match: match.state not in ("done", "cancelled")
        )
        if (unresolved or unfinished) and not force:
            raise ValidationError(
                _(
                    "Resolve incidents and complete or cancel every published "
                    "match before closing."
                )
            )
        if force and not (close_note or "").strip():
            raise ValidationError(
                _("A close reason is required when overriding match-day blockers.")
            )
        session = matchday.active_session_id
        transition = self.env["federation.workflow.transition"]
        session_result = transition.execute(
            session.sudo(),
            "closed",
            {"open"},
            values={
                "closed_at": fields.Datetime.now(),
                "closed_by_id": self.env.user.id,
                "close_note": close_note,
            },
            reason=close_note,
            reason_required=bool(force),
            event_type="matchday_session_closed",
            description=_("Match-day execution session closed."),
        )
        result = transition.execute(
            matchday.sudo(),
            "closed",
            {"open"},
            reason=close_note,
            reason_required=bool(force),
            event_type="matchday_closed",
            description=_("Match-day operations closed."),
        )
        self.env["federation.competition.event"].emit(
            matchday,
            "matchday_closed",
            {
                "session_id": session.id,
                "forced": bool(force),
                "unfinished_match_ids": unfinished.ids,
                "unresolved_incident_ids": unresolved.ids,
            },
        )
        result.update(
            {
                "session_id": session.id,
                "session_result": session_result,
                "forced": bool(force),
                "unfinished_match_ids": unfinished.ids,
                "unresolved_incident_ids": unresolved.ids,
            }
        )
        return result
