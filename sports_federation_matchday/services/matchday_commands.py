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
        session = self.env["federation.matchday.session"].create(
            {
                "matchday_id": matchday.id,
                "publication_id": publication.id,
                "publication_digest": publication.snapshot_digest,
            }
        )
        for court in matchday.slot_ids.mapped("court_id"):
            self.env["federation.matchday.court.status"].create(
                {"matchday_id": matchday.id, "court_id": court.id}
            )
        matchday.state = "open"
        self.env["federation.competition.event"].emit(
            matchday,
            "matchday_opened",
            {"session_id": session.id, "publication_id": publication.id},
        )
        return session

    @api.model
    def report_incident(self, matchday_id, incident_type, description):
        matchday = self._resolve(matchday_id)
        self._require_open(matchday)
        return self.env["federation.matchday.incident"].create(
            {
                "matchday_id": matchday.id,
                "incident_type": incident_type,
                "description": description,
            }
        )

    @api.model
    def set_court_status(
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
        status.write(
            {
                "state": state,
                "delay_minutes": max(0, int(delay_minutes or 0)),
                "note": note,
            }
        )
        if state != "available":
            self.report_incident(
                matchday.id,
                "court_unavailable" if state == "unavailable" else "delay",
                note or _("Court status changed."),
            )
        return status

    @api.model
    def resolve_incident(self, incident_id):
        incident = (
            self.env["federation.matchday.incident"].browse(int(incident_id)).exists()
        )
        matchday = self._resolve(incident.matchday_id.id)
        self._require_open(matchday)
        incident.write(
            {
                "resolved": True,
                "resolved_at": fields.Datetime.now(),
                "resolved_by_id": self.env.user.id,
            }
        )
        return True

    @api.model
    def close_matchday(self, matchday_id, close_note=False, force=False):
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
                    "Resolve incidents and complete or cancel every published match before closing."
                )
            )
        if force and not (close_note or "").strip():
            raise ValidationError(
                _("A close reason is required when overriding match-day blockers.")
            )
        session = matchday.active_session_id
        session.write(
            {
                "state": "closed",
                "closed_at": fields.Datetime.now(),
                "closed_by_id": self.env.user.id,
                "close_note": close_note,
            }
        )
        matchday.state = "closed"
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
        return True
