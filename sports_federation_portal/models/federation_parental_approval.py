import base64
from collections import defaultdict
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.misc import format_date

# The age rule is owned by roster eligibility (players under 16 need a verified
# parental approval to take part in a senior league); the portal overview only
# mirrors it so clubs can see the answer before a line-up is blocked.
PARENTAL_APPROVAL_AGE = 16
EXPIRY_WARNING_DAYS = 30


class FederationPlayerParentalApprovalPortal(models.Model):
    _inherit = "federation.player.parental.approval"

    @api.model
    def _portal_create_parental_approval(self, player, values, upload, user=None):
        """Create a club-scoped draft from a validated portal upload.

        Verification deliberately remains a federation backend action.  The
        portal actor can only create immutable-at-review draft evidence for a
        player in a currently represented club.
        """
        user = user or self.env.user
        privilege = self.env["federation.portal.privilege"]
        represented_clubs = privilege.elevate(
            self.env["federation.club.representative"], user=user
        )._get_clubs_for_user(user=user)
        player = privilege.portal_assert_in_domain(
            player,
            [("club_id", "in", represented_clubs.ids)],
            _("You can only upload parental approval for players in your club."),
            user=user,
        )
        player.ensure_one()
        if not upload or not getattr(upload, "filename", False):
            raise ValidationError(_("Select a signed approval document to upload."))

        payload = upload.read()
        checked = self.env["federation.attachment.policy"].validate_upload(
            "portal_document",
            upload.filename,
            payload,
            mimetype=getattr(upload, "content_type", False),
        )
        guardian_name = (values.get("guardian_name") or "").strip()
        if not guardian_name:
            raise ValidationError(_("Parent or guardian name is required."))
        approval_date = fields.Date.to_date(values.get("approval_date"))
        valid_until = fields.Date.to_date(values.get("valid_until"))
        if not approval_date:
            raise ValidationError(_("Approval date is required."))

        pending = privilege.portal_search(
            self,
            [("player_id", "=", player.id), ("state", "=", "draft")],
            user=user,
            limit=1,
        )
        if pending:
            raise ValidationError(
                _(
                    "A parental approval for this player is already awaiting federation review."
                )
            )

        approval_values = {
            "player_id": player.id,
            "guardian_name": guardian_name,
            "guardian_email": (values.get("guardian_email") or "").strip() or False,
            "approval_date": approval_date,
            "valid_until": valid_until or False,
            "approval_document": base64.b64encode(checked["payload"]),
            "approval_document_filename": checked["filename"],
            "notes": (values.get("notes") or "").strip() or False,
            "state": "draft",
            "submitted_by_id": user.id,
            "submitted_on": fields.Datetime.now(),
        }
        return privilege.portal_create(self, approval_values, user=user)

    # ------------------------------------------------------------------
    # Club overview: who needs parental approval
    # ------------------------------------------------------------------

    @api.model
    def _portal_player_overview(self, players, user=None, reference_date=None):
        """Describe, per player, whether a parental approval is needed.

        Mirrors the roster eligibility rule: a player under 16 on the reference
        date needs a verified approval that covers that date before playing in a
        senior (adult) league. The overview only reads what the club
        representative may already see for their own club's players.

        Returns a dict with ``by_player`` (player id -> display values),
        ``counts``, ``tiles`` and ``bar`` for the summary card, and ``summary``
        (a sentence for assistive technology).
        """
        user = user or self.env.user
        privilege = self.env["federation.portal.privilege"]
        represented_clubs = privilege.elevate(
            self.env["federation.club.representative"], user=user
        )._get_clubs_for_user(user=user)
        players = players.filtered(lambda player: player.club_id in represented_clubs)
        elevated = privilege.elevate(players, user=user)
        today = reference_date or fields.Date.context_today(self)

        minors = elevated.filtered(
            lambda player: player.birth_date
            and player._is_under_age(PARENTAL_APPROVAL_AGE, today)
        )
        approvals = defaultdict(list)
        senior_teams = defaultdict(list)
        if minors:
            Approval = elevated.env["federation.player.parental.approval"]
            for approval in Approval.search(
                [("player_id", "in", minors.ids)], order="approval_date desc, id desc"
            ):
                approvals[approval.player_id.id].append(approval)
            Line = elevated.env["federation.team.roster.line"]
            for line in Line.search(
                [
                    ("player_id", "in", minors.ids),
                    ("status", "=", "active"),
                    ("roster_id.status", "!=", "closed"),
                    ("team_id.category", "=", "senior"),
                    "|",
                    ("season_id.date_end", "=", False),
                    ("season_id.date_end", ">=", today),
                ]
            ):
                name = line.team_id.display_name
                if name not in senior_teams[line.player_id.id]:
                    senior_teams[line.player_id.id].append(name)

        by_player = {}
        counts = dict.fromkeys(
            (
                "total",
                "under_age",
                "approved",
                "expiring",
                "pending",
                "needed_now",
                "needed_later",
                "needs_action",
                "no_birth_date",
            ),
            0,
        )
        counts["total"] = len(elevated)
        for player in elevated:
            info = self._portal_player_overview_line(
                player,
                player in minors,
                approvals.get(player.id, []),
                senior_teams.get(player.id, []),
                today,
            )
            by_player[player.id] = info
            if info["key"] == "no_birth_date":
                counts["no_birth_date"] += 1
            if not info["under_age"]:
                continue
            counts["under_age"] += 1
            if info["key"] in ("approved", "expiring"):
                counts["approved"] += 1
            if info["key"] == "expiring":
                counts["expiring"] += 1
            if info["key"] == "pending":
                counts["pending"] += 1
            if info["needs_action"]:
                counts["needed_now" if info["level"] == "danger" else "needed_later"] += 1
        counts["needs_action"] = counts["needed_now"] + counts["needed_later"]
        return {
            "by_player": by_player,
            "counts": counts,
            "tiles": self._portal_overview_tiles(counts),
            "bar": self._portal_overview_bar(counts),
            "summary": _(
                "%(approved)s of %(total)s players under %(age)s have a valid parental "
                "approval; %(action)s need action and %(pending)s await review.",
                approved=counts["approved"],
                total=counts["under_age"],
                age=PARENTAL_APPROVAL_AGE,
                action=counts["needs_action"],
                pending=counts["pending"],
            ),
        }

    @api.model
    def _portal_player_overview_line(self, player, under_age, approvals, teams, today):
        """Return the display values of one player (see the overview above)."""
        base = {
            "under_age": under_age,
            "age_label": _("Under %s", PARENTAL_APPROVAL_AGE),
            "age_note": False,
            "show_badge": True,
            "needs_action": False,
            "row_class": "",
            "cta": _("Manage document"),
            "cta_class": "btn-outline-secondary",
        }
        if not player.birth_date:
            return dict(
                base,
                key="no_birth_date",
                level="muted",
                badge="text-bg-secondary",
                icon="fa-question-circle",
                label=_("Birth date missing"),
                detail=_("Add the birth date so the age rule can be checked."),
            )
        if not under_age:
            return dict(
                base,
                key="not_required",
                level="ok",
                badge="text-bg-light border",
                icon="fa-check",
                label=_("Not required"),
                detail=False,
                show_badge=False,
            )

        turns = self._portal_birthday(player.birth_date, PARENTAL_APPROVAL_AGE)
        base["age_note"] = _(
            "Under %(age)s until %(date)s",
            age=PARENTAL_APPROVAL_AGE,
            date=format_date(self.env, turns),
        )
        playing = ", ".join(teams)
        if player._has_verified_parental_approval(today):
            covering = next(
                (
                    approval
                    for approval in approvals
                    if approval.state == "verified"
                    and (not approval.valid_until or approval.valid_until >= today)
                ),
                False,
            )
            valid_until = covering and covering.valid_until
            if valid_until and (valid_until - today).days <= EXPIRY_WARNING_DAYS:
                return dict(
                    base,
                    key="expiring",
                    level="warning",
                    badge="text-bg-warning",
                    icon="fa-clock-o",
                    label=_("Approved, expires soon"),
                    detail=_(
                        "Valid until %(date)s (%(days)s days left).",
                        date=format_date(self.env, valid_until),
                        days=(valid_until - today).days,
                    ),
                    cta=_("Upload renewal"),
                    cta_class="btn-outline-warning",
                )
            return dict(
                base,
                key="approved",
                level="ok",
                badge="text-bg-success",
                icon="fa-check-circle",
                label=_("Approved"),
                detail=(
                    _("Valid until %s.", format_date(self.env, valid_until))
                    if valid_until
                    else _("No expiry date.")
                ),
            )

        pending = any(approval.state == "draft" for approval in approvals)
        if pending:
            return dict(
                base,
                key="pending",
                level="info",
                badge="text-bg-info",
                icon="fa-hourglass-half",
                label=_("Awaiting review"),
                detail=(
                    _(
                        "Not valid until the federation verifies it. On %s.",
                        playing,
                    )
                    if playing
                    else _("Not valid until the federation verifies it.")
                ),
                cta=_("View status"),
            )

        latest = approvals[0] if approvals else False
        if latest and latest.state == "replacement_requested":
            key, label, icon = "replacement", _("Replacement needed"), "fa-refresh"
            detail = (latest.review_note or "").strip() or _(
                "The federation asked for a new document."
            )
        elif any(approval.state == "verified" for approval in approvals):
            expired = next(
                (
                    approval
                    for approval in approvals
                    if approval.state == "verified" and approval.valid_until
                ),
                False,
            )
            key, label, icon = "expired", _("Approval expired"), "fa-calendar-times-o"
            detail = (
                _("Expired on %s.", format_date(self.env, expired.valid_until))
                if expired
                else _("The last approval does not cover today.")
            )
        elif any(approval.state == "revoked" for approval in approvals):
            key, label, icon = "revoked", _("Approval revoked"), "fa-ban"
            detail = _("The federation revoked the last approval.")
        else:
            key, label, icon = "missing", _("Approval needed"), "fa-exclamation-circle"
            detail = (
                _("Plays in %s. Upload a signed approval.", playing)
                if playing
                else _("Needed before they play in a senior team.")
            )
        if playing and key != "missing":
            detail = "%s %s" % (detail, _("On %s.", playing))
        urgent = bool(playing)
        return dict(
            base,
            key=key,
            level="danger" if urgent else "warning",
            badge="text-bg-danger" if urgent else "text-bg-warning",
            icon=icon,
            label=label,
            detail=detail,
            needs_action=True,
            row_class="table-danger" if urgent else "table-warning",
            cta=_("Upload approval"),
            cta_class="btn-primary" if urgent else "btn-outline-primary",
        )

    @api.model
    def _portal_birthday(self, birth_date, years):
        """Return the date a player reaches ``years`` (29 February: 1 March)."""
        try:
            return birth_date.replace(year=birth_date.year + years)
        except ValueError:
            return date(birth_date.year + years, 3, 1)

    @api.model
    def _portal_overview_tiles(self, counts):
        tiles = [
            {
                "css": "border-danger bg-danger-subtle",
                "icon": "fa-exclamation-circle text-danger",
                "count": counts["needed_now"],
                "label": _("Needed now"),
                "hint": _("On a senior roster without a valid approval."),
            },
            {
                "css": "border-warning bg-warning-subtle",
                "icon": "fa-exclamation-triangle text-warning",
                "count": counts["needed_later"],
                "label": _("Needed for senior play"),
                "hint": _("Not on a senior roster, but would need one to play there."),
            },
            {
                "css": "border-info bg-info-subtle",
                "icon": "fa-hourglass-half text-info",
                "count": counts["pending"],
                "label": _("Awaiting review"),
                "hint": _("Uploaded; the federation still has to verify it."),
            },
            {
                "css": "border-success bg-success-subtle",
                "icon": "fa-check-circle text-success",
                "count": counts["approved"],
                "label": _("Approved"),
                "hint": (
                    _("%s expire within 30 days.", counts["expiring"])
                    if counts["expiring"]
                    else _("Valid today.")
                ),
            },
        ]
        if counts["no_birth_date"]:
            tiles.append(
                {
                    "css": "border-secondary bg-body-secondary",
                    "icon": "fa-question-circle text-secondary",
                    "count": counts["no_birth_date"],
                    "label": _("Birth date missing"),
                    "hint": _("The age rule cannot be checked."),
                }
            )
        return tiles

    @api.model
    def _portal_overview_bar(self, counts):
        """Segments of the stacked bar over the players under the age limit."""
        total = counts["under_age"]
        if not total:
            return []
        segments = (
            ("bg-danger", counts["needed_now"], _("Needed now")),
            ("bg-warning", counts["needed_later"], _("Needed for senior play")),
            ("bg-info", counts["pending"], _("Awaiting review")),
            ("bg-success", counts["approved"], _("Approved")),
        )
        return [
            {
                "css": css,
                "count": count,
                "pct": round(100.0 * count / total, 1),
                "label": "%s: %s" % (label, count),
            }
            for css, count, label in segments
            if count
        ]
