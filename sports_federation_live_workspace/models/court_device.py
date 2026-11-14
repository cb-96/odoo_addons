"""Offline court scoring on personal phones.

Who may score a match is derived per match, at every request:

* the head referee and assistant referees with a confirmed assignment
  (``federation.match.referee``) and a linked portal account;
* an optional club scorer nominated by a club representative of one of the
  two clubs (``federation.match.scorer``);
* a named court operator of the match's court (backend court app).

A phone gets a device token for one game day through a one-time code, issued
while the scorer is logged in. The token only reaches the device service in
this file; every request re-checks the token, the game day, the scorer's
rights for the match and the open match-day session. Results captured on
court always wait for the tournament manager (one-step approval).
"""

import hashlib
import hmac
import re
import secrets
from datetime import datetime, time, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.addons.sports_federation_base.models.request_rate_limit import (
    FederationRequestRateLimit as BaseRateLimit,
)

from ..policy import (
    LOG_EVENT_TYPES,
    digest,
    validate_device_command,
    validate_match_log,
    validate_participation,
)
from .court import _CONTEXT, _TOKEN

SCORING_ROLES = ("head", "assistant_1", "assistant_2")
SCORER_SOURCES = [
    ("head_referee", "Head referee"),
    ("assistant_referee", "Assistant referee"),
    ("club_scorer", "Club scorer"),
    ("court_operator", "Court operator"),
]
CODE_LIFETIME = timedelta(minutes=10)
# A token is valid for its game day only, with a margin for late syncs.
TOKEN_MARGIN = timedelta(days=1)
PIN_RE = re.compile(r"^\d{4,6}$")
PIN_ITERATIONS = 200_000
PIN_MAX_FAILURES = 5
PIN_LOCK = timedelta(minutes=15)
COURT_RATE_LIMITS = {
    # Activation is guessed only by brute force: keep it tight per address.
    "court_activate": {"limit": 10, "window_seconds": 60},
    # A venue may share one address for many phones (one Wi-Fi network).
    "court_pack": {"limit": 120, "window_seconds": 60},
    "court_sync": {"limit": 600, "window_seconds": 60},
}


def _hash_secret(value):
    return hashlib.sha256((value or "").encode()).hexdigest()


class MatchScorer(models.Model):
    """Optional club scorer for one match, nominated by a club representative."""

    _name = "federation.match.scorer"
    _description = "Club Scorer Nomination"
    _order = "id desc"

    match_id = fields.Many2one(
        "federation.match", required=True, ondelete="cascade", index=True
    )
    user_id = fields.Many2one(
        "res.users", string="Scorer", required=True, ondelete="restrict", index=True
    )
    club_id = fields.Many2one(
        "federation.club", required=True, ondelete="restrict", index=True
    )
    nominated_by_id = fields.Many2one(
        "res.users", required=True, ondelete="restrict", readonly=True
    )
    active = fields.Boolean(default=True)
    withdrawn_by_id = fields.Many2one("res.users", readonly=True, ondelete="restrict")
    withdrawn_on = fields.Datetime(readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_("Nominate club scorers through the court duty page."))
        return super().create(vals_list)

    def write(self, values):
        if not self.env.su and not self.env.user.has_group(
            "sports_federation_matchday.group_matchday_manager"
        ):
            raise AccessError(_("Withdraw club scorers through the court duty page."))
        if {"match_id", "user_id", "club_id"}.intersection(values):
            raise ValidationError(_("Withdraw the nomination and nominate again."))
        return super().write(values)

    @api.ondelete(at_uninstall=False)
    def _retain(self):
        raise ValidationError(
            _("Withdraw club scorer nominations; keep their history.")
        )

    def action_withdraw(self):
        """Withdraw from the backend (match-day managers of the competition)."""
        for scorer in self:
            self.env["federation.competition.role.assignment"].assert_role(
                scorer.match_id._competition_workflow_edition(),
                "matchday_manager",
                "competition_director",
            )
        self.write(
            {
                "active": False,
                "withdrawn_by_id": self.env.uid,
                "withdrawn_on": fields.Datetime.now(),
            }
        )
        return True


class CourtDevice(models.Model):
    """A phone prepared to score one game day offline."""

    _name = "federation.court.device"
    _description = "Court Scoring Device"
    _order = "id desc"

    user_id = fields.Many2one(
        "res.users", string="Scorer", required=True, ondelete="restrict", index=True
    )
    matchday_id = fields.Many2one(
        "federation.matchday", required=True, ondelete="restrict", index=True
    )
    label = fields.Char(required=True, default="Phone")
    state = fields.Selection(
        [
            ("pending", "Waiting for the phone"),
            ("active", "Active"),
            ("revoked", "Revoked"),
            ("expired", "Expired"),
        ],
        default="pending",
        required=True,
        readonly=True,
        index=True,
    )
    code_hash = fields.Char(readonly=True, copy=False)
    code_expires_at = fields.Datetime(readonly=True, copy=False)
    token_hash = fields.Char(readonly=True, copy=False, index=True)
    expires_at = fields.Datetime(required=True, readonly=True)
    activated_on = fields.Datetime(readonly=True)
    last_seen_at = fields.Datetime(readonly=True)
    user_agent = fields.Char(readonly=True)
    revoked_on = fields.Datetime(readonly=True)
    revoked_by_id = fields.Many2one("res.users", readonly=True, ondelete="restrict")
    capture_ids = fields.One2many(
        "federation.court.capture", "device_id", readonly=True
    )

    _token_unique = models.Constraint(
        "unique(token_hash)", "A device token can only be issued once."
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_("Prepare a phone from the court duty page."))
        return super().create(vals_list)

    def write(self, values):
        if not self.env.su:
            raise AccessError(_("Use Revoke to stop a court device."))
        return super().write(values)

    @api.ondelete(at_uninstall=False)
    def _retain(self):
        raise ValidationError(_("Court devices are kept as scoring evidence."))

    def action_revoke(self):
        """Revoke from the backend (match-day managers) or the portal (owner)."""
        for device in self:
            manager = self.env.user.has_group(
                "sports_federation_matchday.group_matchday_manager"
            )
            if device.user_id != self.env.user and not manager:
                raise AccessError(_("You can only revoke your own devices."))
            if manager and device.user_id != self.env.user:
                self.env["federation.competition.role.assignment"].assert_role(
                    device.matchday_id.edition_id,
                    "matchday_manager",
                    "competition_director",
                )
        self.sudo()._revoke()
        return True

    def _revoke(self):
        live = self.filtered(lambda device: device.state in ("pending", "active"))
        live.write(
            {
                "state": "revoked",
                "revoked_on": fields.Datetime.now(),
                "revoked_by_id": self.env.uid,
                "code_hash": False,
            }
        )

    @api.model
    def _cron_expire(self):
        now = fields.Datetime.now()
        devices = self.sudo()
        devices.search(
            [("state", "=", "pending"), ("code_expires_at", "<", now)]
        ).write({"state": "expired", "code_hash": False})
        devices.search([("state", "=", "active"), ("expires_at", "<", now)]).write(
            {"state": "expired"}
        )
        return True


class RefereeCourtPin(models.Model):
    """Head-referee PIN used to confirm a result scored by someone else."""

    _inherit = "federation.referee"

    court_pin_hash = fields.Char(groups="base.group_system", copy=False)
    court_pin_set_on = fields.Datetime(readonly=True, copy=False)
    court_pin_failures = fields.Integer(groups="base.group_system", copy=False)
    court_pin_locked_until = fields.Datetime(groups="base.group_system", copy=False)

    @staticmethod
    def _court_pin_digest(pin, salt, iterations=PIN_ITERATIONS):
        return hashlib.pbkdf2_hmac(
            "sha256", pin.encode(), bytes.fromhex(salt), iterations
        ).hex()

    def _set_court_pin(self, pin):
        self.ensure_one()
        pin = (pin or "").strip()
        if not PIN_RE.match(pin):
            raise ValidationError(_("Use a PIN of 4 to 6 digits."))
        if len(set(pin)) == 1 or pin in "0123456789" or pin in "9876543210":
            raise ValidationError(_("Choose a PIN that is not a simple sequence."))
        salt = secrets.token_hex(16)
        self.sudo().write(
            {
                "court_pin_hash": "pbkdf2$%s$%s$%s"
                % (PIN_ITERATIONS, salt, self._court_pin_digest(pin, salt)),
                "court_pin_set_on": fields.Datetime.now(),
                "court_pin_failures": 0,
                "court_pin_locked_until": False,
            }
        )
        return True

    def _check_court_pin(self, pin):
        """Return True for the right PIN; lock after repeated failures."""
        self.ensure_one()
        referee = self.sudo()
        now = fields.Datetime.now()
        if not referee.court_pin_hash or (
            referee.court_pin_locked_until and referee.court_pin_locked_until > now
        ):
            return False
        try:
            _scheme, iterations, salt, expected = referee.court_pin_hash.split("$")
            actual = self._court_pin_digest(str(pin or ""), salt, int(iterations))
        except (ValueError, TypeError):
            return False
        if hmac.compare_digest(actual, expected):
            referee.write({"court_pin_failures": 0})
            return True
        failures = referee.court_pin_failures + 1
        referee.write(
            {
                "court_pin_failures": 0 if failures >= PIN_MAX_FAILURES else failures,
                "court_pin_locked_until": (
                    now + PIN_LOCK if failures >= PIN_MAX_FAILURES else False
                ),
            }
        )
        return False


class CourtCaptureEvidence(models.Model):
    _inherit = "federation.court.capture"

    device_id = fields.Many2one(
        "federation.court.device", readonly=True, ondelete="restrict", index=True
    )
    scorer_user_id = fields.Many2one("res.users", readonly=True, ondelete="restrict")
    scorer_source = fields.Selection(SCORER_SOURCES, readonly=True)
    scorer_club_id = fields.Many2one(
        "federation.club", string="Scorer's club", readonly=True, ondelete="restrict"
    )
    referee_confirmation = fields.Selection(
        [
            ("head_referee", "Scored by the head referee"),
            ("pin", "Confirmed with the head referee's PIN"),
            ("none", "Not confirmed by the head referee"),
        ],
        readonly=True,
    )
    referee_confirmed_by_id = fields.Many2one(
        "federation.referee", readonly=True, ondelete="restrict"
    )
    match_log = fields.Json(
        default=list, help="Cards, time-outs and challenges recorded on court."
    )
    conflict_count = fields.Integer(readonly=True)
    receipt_ids = fields.One2many(
        "federation.court.receipt", "capture_id", readonly=True
    )
    scorer_club_note = fields.Char(compute="_compute_scorer_club_note")
    evidence_summary = fields.Text(compute="_compute_evidence_summary")

    @api.depends("payload", "match_log", "match_id")
    def _compute_evidence_summary(self):
        labels = {
            "card_blue": _("Blue card"),
            "card_yellow": _("Yellow card"),
            "card_red": _("Red card"),
            "team_card_yellow": _("Team yellow card"),
            "team_card_red": _("Team red card"),
            "staff_card_yellow": _("Staff yellow card"),
            "staff_card_red": _("Staff red card"),
            "timeout": _("Time-out"),
            "challenge": _("Challenge"),
        }
        for capture in self:
            match = capture.match_id.sudo()
            payload = capture.payload or {}
            edition = match._competition_workflow_edition()
            win, draw = edition.court_set_win_points, edition.court_set_draw_points
            lines = []
            for index, period in enumerate(payload.get("periods") or [], 1):
                home, away = period.get("home", 0), period.get("away", 0)
                if edition.court_scoring_mode == "sets":
                    points = (
                        (draw, draw)
                        if home == away
                        else ((win, 0) if home > away else (0, win))
                    )
                    lines.append(
                        _("Set %(n)s: %(h)s – %(a)s%(draw)s → %(ph)s – %(pa)s points")
                        % {
                            "n": index,
                            "h": home,
                            "a": away,
                            "draw": _(" (draw)") if home == away else "",
                            "ph": points[0],
                            "pa": points[1],
                        }
                    )
                else:
                    lines.append(
                        _("Period %(n)s: %(h)s – %(a)s")
                        % {"n": index, "h": home, "a": away}
                    )
            lines.append(
                _("Match score: %(h)s – %(a)s · %(outcome)s")
                % {
                    "h": payload.get("home", 0),
                    "a": payload.get("away", 0),
                    "outcome": payload.get("outcome", "normal"),
                }
            )
            if payload.get("reason"):
                lines.append(_("Reason: %s") % payload["reason"])
            for sheet in match.match_sheet_ids:
                out = sheet.line_ids.filtered("crossed_out")
                lines.append(
                    _("%(team)s: %(playing)s playing, crossed out: %(out)s")
                    % {
                        "team": sheet.team_id.display_name,
                        "playing": len(sheet.line_ids) - len(out),
                        "out": ", ".join(out.mapped("player_id.display_name")) or "-",
                    }
                )
            players = {
                line.player_id.id: line.player_id.display_name
                for line in match.match_sheet_ids.line_ids
            }
            for event in capture.match_log or []:
                team = (
                    match.home_team_id
                    if event.get("side") == "home"
                    else match.away_team_id
                ).display_name
                parts = [labels.get(event.get("type"), event.get("type")), team]
                if event.get("player_id"):
                    parts.append(
                        players.get(event["player_id"], "#%s" % event["player_id"])
                    )
                if event.get("half"):
                    parts.append(_("half %s") % event["half"])
                if event.get("set"):
                    parts.append(_("set %s") % event["set"])
                lines.append(" · ".join(str(part) for part in parts))
            capture.evidence_summary = "\n".join(lines)

    @api.depends("scorer_club_id", "match_id")
    def _compute_scorer_club_note(self):
        for capture in self:
            club = capture.scorer_club_id
            match = capture.match_id
            if not club:
                capture.scorer_club_note = False
            elif club == match.home_team_id.club_id:
                capture.scorer_club_note = _("Scored by the home club")
            elif club == match.away_team_id.club_id:
                capture.scorer_club_note = _("Scored by the away club")
            else:
                capture.scorer_club_note = False


class CourtReceiptDevice(models.Model):
    _inherit = "federation.court.receipt"

    device_id = fields.Many2one(
        "federation.court.device", readonly=True, ondelete="restrict", index=True
    )


class MatchCourtScoring(models.Model):
    _inherit = "federation.match"

    court_capture_ids = fields.One2many(
        "federation.court.capture", "match_id", readonly=True
    )
    court_scorer_ids = fields.One2many(
        "federation.match.scorer", "match_id", readonly=True
    )

    def action_approve_result_one_step(self):
        """Prevent a court scorer from approving their own captured result."""
        own_captures = self.sudo().mapped("court_capture_ids").filtered(
            lambda capture: capture.submitted
            and capture.scorer_user_id == self.env.user
        )
        if own_captures:
            raise ValidationError(
                _("The scorer who submitted a court result cannot approve it.")
            )
        return super().action_approve_result_one_step()

    def _court_scoring_source(self, user):
        """Return (source, club) when ``user`` may score this match, else (False, None)."""
        self.ensure_one()
        match = self.sudo()
        if not user or not user.active:
            return False, None
        assignments = match.referee_assignment_ids.filtered(
            lambda item: item.state in ("confirmed", "done")
            and item.role in SCORING_ROLES
            and item.referee_id.user_id == user
        )
        if assignments.filtered(lambda item: item.role == "head"):
            return "head_referee", None
        if assignments:
            return "assistant_referee", None
        nomination = (
            self.env["federation.match.scorer"]
            .sudo()
            .search(
                [
                    ("match_id", "=", match.id),
                    ("user_id", "=", user.id),
                    ("active", "=", True),
                ],
                limit=1,
            )
        )
        if nomination:
            return "club_scorer", nomination.club_id
        slot = match.operational_slot_id or match.published_slot_id
        matchday = match.schedule_publication_id.matchday_id
        if slot and matchday and not user.share:
            operator = (
                self.env["federation.court.access"]
                .sudo()
                .search_count(
                    [
                        ("matchday_id", "=", matchday.id),
                        ("court_id", "=", slot.court_id.id),
                        ("user_id", "=", user.id),
                        ("active", "=", True),
                    ]
                )
            )
            if operator:
                return "court_operator", None
        return False, None

    def _court_head_referee(self):
        self.ensure_one()
        head = self.sudo().referee_assignment_ids.filtered(
            lambda item: item.role == "head" and item.state in ("confirmed", "done")
        )[:1]
        return head.referee_id

    def _court_is_current(self):
        """Published on the live publication of its game day and still playable."""
        self.ensure_one()
        match = self.sudo()
        matchday = match.schedule_publication_id.matchday_id
        slot = match.operational_slot_id or match.published_slot_id
        return bool(
            matchday
            and match.schedule_publication_id == matchday.current_publication_id
            and slot
            and match.operational_status not in ("cancelled", "postponed")
        )


class CourtRateLimits(models.Model):
    _inherit = "federation.request.rate.limit"

    _POLICIES = {**BaseRateLimit._POLICIES, **COURT_RATE_LIMITS}


class CourtDeviceService(models.AbstractModel):
    """Every offline-court request goes through this service.

    Only private methods: nothing here is callable over JSON-RPC. Controllers
    authenticate the device and call these methods with the scorer as user.
    """

    _name = "federation.court.device.service"
    _description = "Offline Court Device Service"

    # ── Duties and preparation (scorer logged in) ────────────────────────
    @api.model
    def _court_duties(self, user=None):
        """Game days with matches the user may score, for the portal page."""
        user = user or self.env.user
        today = fields.Date.context_today(self)
        Match = self.env["federation.match"].sudo()
        candidates = Match.search(
            [
                "|",
                ("referee_assignment_ids.referee_id.user_id", "=", user.id),
                (
                    "court_scorer_ids",
                    "any",
                    [("user_id", "=", user.id), ("active", "=", True)],
                ),
                (
                    "schedule_publication_id.matchday_id.date",
                    ">=",
                    today - timedelta(days=1),
                ),
            ],
            order="date_scheduled,id",
            limit=200,
        )
        if not user.share:
            # Named court operators score every match on their court.
            accesses = (
                self.env["federation.court.access"]
                .sudo()
                .search(
                    [
                        ("user_id", "=", user.id),
                        ("active", "=", True),
                        ("matchday_id.date", ">=", today - timedelta(days=1)),
                    ]
                )
            )
            publications = accesses.mapped("matchday_id.current_publication_id")
            if publications:
                candidates |= Match.search(
                    [("schedule_publication_id", "in", publications.ids)],
                    order="date_scheduled,id",
                    limit=200,
                )
        days = {}
        for match in candidates:
            if not match._court_is_current():
                continue
            source, club = match._court_scoring_source(user)
            if not source:
                continue
            matchday = match.schedule_publication_id.matchday_id
            day = days.setdefault(matchday.id, {"matchday": matchday, "matches": []})
            day["matches"].append({"match": match, "source": source, "club": club})
        return sorted(
            days.values(), key=lambda day: (day["matchday"].date, day["matchday"].id)
        )

    @api.model
    def _prepare_device(self, matchday_id, label=None, user_agent=None):
        """Create a pending device and return its one-time code (shown once)."""
        user = self.env.user
        if user._is_public():
            raise AccessError(_("Log in to prepare a phone."))
        matchday = (
            self.env["federation.matchday"].sudo().browse(int(matchday_id)).exists()
        )
        if not matchday or not any(
            day["matchday"] == matchday for day in self._court_duties(user)
        ):
            raise AccessError(_("You have no matches to score on this game day."))
        code = secrets.token_urlsafe(24)
        expires = datetime.combine(matchday.date, time(23, 59, 59)) + TOKEN_MARGIN
        self.env["federation.court.device"].sudo().create(
            {
                "user_id": user.id,
                "matchday_id": matchday.id,
                "label": (label or "Phone").strip()[:60] or "Phone",
                "code_hash": _hash_secret(code),
                "code_expires_at": fields.Datetime.now() + CODE_LIFETIME,
                "expires_at": expires,
                "user_agent": (user_agent or "")[:250],
            }
        )
        return code

    @api.model
    def _activate(self, code, user_agent=None):
        """Exchange a one-time code for the device token (returned once)."""
        Device = self.env["federation.court.device"].sudo()
        device = Device.search(
            [("code_hash", "=", _hash_secret(code)), ("state", "=", "pending")],
            limit=1,
        )
        if not device or device.code_expires_at < fields.Datetime.now():
            raise AccessError(_("This preparation code is invalid or expired."))
        token = secrets.token_urlsafe(32)
        device.write(
            {
                "state": "active",
                "code_hash": False,
                "token_hash": _hash_secret(token),
                "activated_on": fields.Datetime.now(),
                "last_seen_at": fields.Datetime.now(),
                "user_agent": (user_agent or device.user_agent or "")[:250],
            }
        )
        return device, token

    @api.model
    def _authenticate(self, token):
        """Return the active device for a bearer token, or raise AccessError."""
        if not token or len(token) > 200:
            raise AccessError(_("Device token missing."))
        device = (
            self.env["federation.court.device"]
            .sudo()
            .search([("token_hash", "=", _hash_secret(token))], limit=1)
        )
        now = fields.Datetime.now()
        if not device or device.state != "active":
            raise AccessError(_("This phone is no longer prepared. Prepare it again."))
        if device.expires_at < now:
            # Raising rolls this request back, so the state change is left to
            # ``_cron_expire``; the token is refused either way.
            raise AccessError(_("This phone's game day has ended. Prepare it again."))
        if not device.user_id.active:
            raise AccessError(_("The scorer's account is no longer active."))
        device.write({"last_seen_at": now})
        return device

    # ── Pack (offline game day) ──────────────────────────────────────────
    def _scorable_matches(self, device):
        matchday = device.matchday_id
        matches = (
            self.env["federation.match"]
            .sudo()
            .search(
                [("schedule_publication_id", "=", matchday.current_publication_id.id)],
                order="date_scheduled,id",
            )
        )
        return matches.filtered(
            lambda match: match._court_is_current()
            and match._court_scoring_source(device.user_id)[0]
        )

    @api.model
    def _pack(self, device):
        """Everything one scorer needs for the game day, with minimal personal data."""
        matchday = device.matchday_id
        Commands = self.env["federation.court.commands"]
        rows = []
        for match in self._scorable_matches(device):
            source, _club = match._court_scoring_source(device.user_id)
            capture = (
                self.env["federation.court.capture"]
                .sudo()
                .search([("match_id", "=", match.id)], limit=1)
            )
            slot = match.operational_slot_id or match.published_slot_id
            edition = match._competition_workflow_edition()
            head = match._court_head_referee()
            rows.append(
                {
                    "id": match.id,
                    "name": match.display_name,
                    "home": match.home_team_id.display_name,
                    "away": match.away_team_id.display_name,
                    "court": slot.court_id.display_name,
                    "start": str(slot.start_datetime),
                    "end": str(slot.end_datetime),
                    "result_state": match.result_state,
                    "source": source,
                    "head_referee": (
                        {"id": head.id, "name": head.display_name} if head else None
                    ),
                    "officials": [
                        {"name": item.referee_id.display_name, "role": item.role}
                        for item in match.referee_assignment_ids
                        if item.state != "cancelled"
                    ],
                    "scoring": {
                        "mode": edition.court_scoring_mode,
                        "set_target": edition.court_set_target,
                        "set_points": [
                            edition.court_set_win_points,
                            edition.court_set_draw_points,
                        ],
                        "max_periods": edition.court_max_periods,
                    },
                    "lineups": self._pack_lineups(match),
                    "capture": {
                        "revision": capture.revision if capture else 0,
                        "payload": (
                            capture.payload
                            if capture
                            else {
                                "home": match.home_score,
                                "away": match.away_score,
                                "periods": [],
                                "outcome": "normal",
                                "reason": "",
                                "zero_confirmed": False,
                            }
                        ),
                        "match_log": capture.match_log if capture else [],
                        "submitted": bool(capture and capture.submitted),
                        "closed": bool(capture and capture.closed),
                        "device_id": capture.device_id.id if capture else False,
                        "this_device": bool(capture and capture.device_id == device),
                    },
                    "signature": Commands._device_signature(match),
                }
            )
        pack = {
            "device": {
                "id": device.id,
                "label": device.label,
                "user": device.user_id.display_name,
                "user_id": device.user_id.id,
                "expires_at": str(device.expires_at),
            },
            "matchday": {
                "id": matchday.id,
                "name": matchday.display_name,
                "date": str(matchday.date),
                "venue": matchday.venue_id.display_name,
                "timezone": matchday.event_timezone or "UTC",
            },
            "matches": rows,
            "log_event_types": sorted(LOG_EVENT_TYPES),
        }
        pack["pack_hash"] = digest(pack)
        pack["issued_at"] = str(fields.Datetime.now())
        return pack

    def _pack_lineups(self, match):
        sheets = (
            self.env["federation.match.sheet"]
            .sudo()
            .search([("match_id", "=", match.id)])
        )
        return [
            {
                "sheet_id": sheet.id,
                "side": sheet.side,
                "team": sheet.team_id.display_name,
                "state": sheet.state,
                "limit": sheet.match_participant_limit,
                # Names and shirt numbers only: no contact or birth data.
                "players": [
                    {
                        "id": line.player_id.id,
                        "name": line.player_id.display_name,
                        "number": line.jersey_number or "",
                        "captain": line.is_captain,
                        "crossed_out": line.crossed_out,
                    }
                    for line in sheet.line_ids
                ],
            }
            for sheet in sheets
        ]

    # ── Sync and claim ───────────────────────────────────────────────────
    def _device_match(self, device, match_id):
        """Re-check rights, game day and session for one match, then lock it."""
        match = self.env["federation.match"].sudo().browse(int(match_id)).exists()
        if not match or match.schedule_publication_id.matchday_id != device.matchday_id:
            raise AccessError(_("This match is not on this phone's game day."))
        # Rights first: someone who may not score the match learns nothing
        # about its state.
        source, _club = match._court_scoring_source(device.user_id)
        if not source:
            raise AccessError(_("You are no longer a scorer for this match."))
        if not match._court_is_current():
            raise ValidationError(
                _("The match was moved, postponed or cancelled. Export and reconcile.")
            )
        session = device.matchday_id.active_session_id
        if (
            not session
            or session.publication_id != device.matchday_id.current_publication_id
        ):
            raise ValidationError(
                _(
                    "The game day is not open. Your scores stay on this phone until it opens."
                )
            )
        match._lock_result_transition()
        match.invalidate_recordset()
        return match, session

    @api.model
    def _sync(self, device, match_id, commands):
        if not isinstance(commands, list) or not 1 <= len(commands) <= 100:
            raise ValidationError(_("Synchronise 1 to 100 commands at a time."))
        Commands = self.env["federation.court.commands"]
        with self.env.cr.savepoint():
            match, session = self._device_match(device, match_id)
            capture = Commands._capture(match, Commands._signature(match, session))
            capture = capture.with_context(**{_CONTEXT: _TOKEN})
            capture.invalidate_recordset()
            if capture.device_id and capture.device_id != device:
                raise ValidationError(
                    _(
                        "This match is being scored on another phone. Take it over "
                        "on this phone, or export your scores."
                    )
                )
            if not capture.device_id:
                capture.write({"device_id": device.id})
            acknowledged = []
            for raw in commands:
                try:
                    command, extra = validate_device_command(raw)
                except ValueError as error:
                    raise ValidationError(str(error)) from error
                if command["operation"] in ("participation", "log"):
                    self._apply_side_command(device, match, capture, command)
                else:
                    Commands._apply_commands(match, session, capture, [command], device)
                    if command["operation"] == "submit":
                        self._record_confirmation(device, match, capture, extra)
                acknowledged.append(command["key"])
            capture.invalidate_recordset()
            return {
                "acknowledged_keys": acknowledged,
                "current": self._device_response(device, match, capture),
            }

    def _apply_side_command(self, device, match, capture, command):
        """Crossed-out players and the match log: idempotent, outside the revision."""
        receipts = (
            self.env["federation.court.receipt"]
            .sudo()
            .with_context(**{_CONTEXT: _TOKEN})
        )
        fingerprint = digest(command)
        replay = receipts.search(
            [("capture_id", "=", capture.id), ("key", "=", command["key"])], limit=1
        )
        if replay:
            if replay.digest != fingerprint or replay.actor_id != self.env.user:
                raise ValidationError(
                    _("Idempotency key was reused for different content or actor.")
                )
            return replay.response
        if capture.submitted or match.result_state not in {"draft", "corrected"}:
            raise ValidationError(_("The result was already submitted."))
        if command["operation"] == "participation":
            try:
                sheets = validate_participation(command["payload"])
            except ValueError as error:
                raise ValidationError(str(error)) from error
            for sheet_id, player_ids in sheets.items():
                sheet = (
                    self.env["federation.match.sheet"].sudo().browse(sheet_id).exists()
                )
                if not sheet or sheet.match_id != match:
                    raise AccessError(_("This line-up is not part of the match."))
                # Authorised above: the scorer may score this match.
                sheet.action_set_crossed_out(player_ids)
            response = {"participation": {str(k): v for k, v in sheets.items()}}
        else:
            try:
                events = validate_match_log(command["payload"])
            except ValueError as error:
                raise ValidationError(str(error)) from error
            capture.write({"match_log": events})
            response = {"match_log_count": len(events)}
        receipts.create(
            {
                "capture_id": capture.id,
                "key": command["key"],
                "digest": fingerprint,
                "actor_id": self.env.uid,
                "operation": command["operation"],
                "response": response,
                "device_id": device.id,
            }
        )
        return response

    def _record_confirmation(self, device, match, capture, extra):
        """Head referee scored it, confirmed with PIN, or not confirmed (never blocks)."""
        source, _club = match._court_scoring_source(device.user_id)
        head = match._court_head_referee()
        confirmation = extra.get("confirmation") or {}
        if source == "head_referee":
            values = {
                "referee_confirmation": "head_referee",
                "referee_confirmed_by_id": head.id,
            }
        elif (
            head
            and confirmation.get("method") == "pin"
            and head._check_court_pin(confirmation.get("pin"))
        ):
            values = {"referee_confirmation": "pin", "referee_confirmed_by_id": head.id}
        else:
            values = {"referee_confirmation": "none", "referee_confirmed_by_id": False}
        capture.write(values)

    @api.model
    def _claim(self, device, match_id):
        """Take over scoring of a match on this phone (explicit handover)."""
        Commands = self.env["federation.court.commands"]
        with self.env.cr.savepoint():
            match, session = self._device_match(device, match_id)
            capture = Commands._capture(match, Commands._signature(match, session))
            capture = capture.with_context(**{_CONTEXT: _TOKEN})
            previous = capture.device_id
            if previous != device:
                capture.write({"device_id": device.id})
                self.env["federation.court.receipt"].sudo().with_context(
                    **{_CONTEXT: _TOKEN}
                ).create(
                    {
                        "capture_id": capture.id,
                        "key": "handover:%s:%s" % (device.id, capture.revision),
                        "digest": digest({"from": previous.id, "to": device.id}),
                        "actor_id": self.env.uid,
                        "operation": "handover",
                        "response": {
                            "from_device": previous.id,
                            "to_device": device.id,
                        },
                        "device_id": device.id,
                    }
                )
            return self._device_response(device, match, capture)

    def _device_response(self, device, match, capture):
        return {
            "match_id": match.id,
            "revision": capture.revision,
            "payload": capture.payload,
            "match_log": capture.match_log or [],
            "signature": self.env["federation.court.commands"]._device_signature(match),
            "submitted": capture.submitted,
            "closed": capture.closed,
            "review_required": capture.review_required,
            "result_state": match.result_state,
            "device_id": capture.device_id.id,
            "this_device": capture.device_id == device,
            "referee_confirmation": capture.referee_confirmation or False,
        }

    # ── Club scorer nominations (club representative logged in) ──────────
    @api.model
    def _club_matches(self, user=None):
        """Current matches of the user's clubs that can get a club scorer."""
        user = user or self.env.user
        clubs = (
            self.env["federation.club.representative"].sudo()._get_clubs_for_user(user)
        )
        if not clubs:
            return []
        today = fields.Date.context_today(self)
        matches = (
            self.env["federation.match"]
            .sudo()
            .search(
                [
                    "|",
                    ("home_team_id.club_id", "in", clubs.ids),
                    ("away_team_id.club_id", "in", clubs.ids),
                    ("schedule_publication_id.matchday_id.date", ">=", today),
                    ("result_state", "in", ("draft", "corrected")),
                ],
                order="date_scheduled,id",
                limit=100,
            )
        )
        rows = []
        for match in matches.filtered(lambda item: item._court_is_current()):
            club = (
                match.home_team_id.club_id
                if match.home_team_id.club_id in clubs
                else match.away_team_id.club_id
            )
            rows.append(
                {
                    "match": match,
                    "club": club,
                    "scorers": match.court_scorer_ids.filtered(
                        lambda item, club=club: item.active and item.club_id == club
                    ),
                    "candidates": self._club_scorer_candidates(club),
                }
            )
        return rows

    def _club_scorer_candidates(self, club):
        reps = (
            self.env["federation.club.representative"]
            .sudo()
            .search(
                [
                    ("club_id", "=", club.id),
                    ("is_current", "=", True),
                    ("user_id", "!=", False),
                ]
            )
        )
        return reps.mapped("user_id")

    @api.model
    def _nominate_scorer(self, match_id, user_id):
        nominator = self.env.user
        match = self.env["federation.match"].sudo().browse(int(match_id)).exists()
        if not match or not match._court_is_current():
            raise ValidationError(_("This match cannot get a scorer any more."))
        clubs = (
            self.env["federation.club.representative"]
            .sudo()
            ._get_clubs_for_user(nominator)
        )
        club = (match.home_team_id.club_id | match.away_team_id.club_id) & clubs
        if not club:
            raise AccessError(_("You do not represent a club playing this match."))
        club = club[:1]
        user = self.env["res.users"].sudo().browse(int(user_id)).exists()
        if not user or user not in self._club_scorer_candidates(club):
            raise ValidationError(
                _("Choose a club member with a portal account as scorer.")
            )
        Scorer = self.env["federation.match.scorer"].sudo()
        existing = Scorer.search(
            [
                ("match_id", "=", match.id),
                ("user_id", "=", user.id),
                ("active", "=", True),
            ],
            limit=1,
        )
        if existing:
            return existing
        return Scorer.create(
            {
                "match_id": match.id,
                "user_id": user.id,
                "club_id": club.id,
                "nominated_by_id": nominator.id,
            }
        )

    @api.model
    def _withdraw_scorer(self, scorer_id):
        scorer = (
            self.env["federation.match.scorer"].sudo().browse(int(scorer_id)).exists()
        )
        clubs = (
            self.env["federation.club.representative"]
            .sudo()
            ._get_clubs_for_user(self.env.user)
        )
        if not scorer or scorer.club_id not in clubs:
            raise AccessError(_("You can only withdraw your club's scorers."))
        scorer.write(
            {
                "active": False,
                "withdrawn_by_id": self.env.uid,
                "withdrawn_on": fields.Datetime.now(),
            }
        )
        return True

    # ── Conflicts and rate limits ────────────────────────────────────────
    @api.model
    def _note_conflict(self, match_id):
        """Count refused phone commands on the capture (shown on the check screen)."""
        try:
            match_id = int(match_id)
        except (TypeError, ValueError):
            return False
        capture = (
            self.env["federation.court.capture"]
            .sudo()
            .with_context(**{_CONTEXT: _TOKEN})
            .search([("match_id", "=", match_id)], limit=1)
        )
        if capture:
            capture.write({"conflict_count": capture.conflict_count + 1})
        return True

    @api.model
    def _rate_limit(self, scope, remote_addr):
        return (
            self.env["federation.request.rate.limit"]
            .sudo()
            .consume(scope, "ip:%s" % (remote_addr or "unknown"))
        )

    # ── Referee PIN and own devices (scorer logged in) ───────────────────
    @api.model
    def _own_referee(self):
        return (
            self.env["federation.referee"]
            .sudo()
            .search([("user_id", "=", self.env.uid)], limit=1)
        )

    @api.model
    def _set_own_pin(self, pin):
        referee = self._own_referee()
        if not referee:
            raise AccessError(_("Only referees set a confirmation PIN."))
        return referee._set_court_pin(pin)

    @api.model
    def _own_devices(self):
        return (
            self.env["federation.court.device"]
            .sudo()
            .search(
                [
                    ("user_id", "=", self.env.uid),
                    ("state", "in", ("pending", "active")),
                ],
                order="id desc",
            )
        )

    @api.model
    def _revoke_own(self, device_id):
        device = self._own_devices().filtered(lambda item: item.id == int(device_id))
        if not device:
            raise AccessError(_("You can only revoke your own devices."))
        device._revoke()
        return True
