from .notification_boundary import notification_effect
from datetime import timedelta
from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.fields import Domain
from .actionable_communications import KIND_SELECTION, _lock
from ..communication_policy import identity, merge_roles


class ActionableCommunicationService(models.AbstractModel):
    _inherit = "federation.notification.service"

    def _club_routes(self, teams):
        teams = teams.sudo().exists()
        routes = []
        reps = (
            self.env["federation.club.representative"]
            .sudo()
            .search(
                [
                    ("is_current", "=", True),
                    ("club_id", "in", teams.mapped("club_id").ids),
                ]
            )
        )
        for rep in reps:
            user = rep.effective_user_id or rep.user_id
            if user and user.active and (not rep.team_id or rep.team_id in teams):
                routes.append((user.id, "club"))
        scoped = (
            self.env["res.users"]
            .sudo()
            .search([("active", "=", True), ("portal_team_scope_ids", "in", teams.ids)])
        )
        routes.extend((user.id, "team") for user in scoped)
        return routes

    def _organiser_routes(self, edition):
        assignments = (
            self.env["federation.competition.role.assignment"]
            .sudo()
            .search(
                [
                    ("edition_id", "=", edition.id),
                    ("active", "=", True),
                    ("role", "in", ["competition_director", "matchday_manager"]),
                ]
            )
        )
        routes = [
            (assignment.user_id.id, assignment.role)
            for assignment in assignments
            if assignment.user_id.active
        ]
        # Managers are an existing authorised fallback, not arbitrary group members.
        if not routes:
            routes = [
                (user.id, "manager")
                for user in self.env.ref(
                    "sports_federation_base.group_federation_manager"
                )
                .sudo()
                .user_ids.filtered("active")
            ]
        return routes

    def _day_matches(self, day):
        publication = day.sudo().current_publication_id
        ids = [
            row.get("match_id")
            for row in (publication.assignment_snapshot or [])
            if row.get("match_id")
        ]
        return self.env["federation.match"].sudo().browse(ids).exists()

    def _day_routes(self, day):
        matches = self._day_matches(day)
        routes = self._club_routes(
            matches.mapped("home_team_id") | matches.mapped("away_team_id")
        )
        officials = (
            self.env["federation.match.referee"]
            .sudo()
            .search(
                [
                    ("match_id", "in", matches.ids),
                    ("publication_id", "=", day.current_publication_id.id),
                    ("state", "in", ["draft", "confirmed"]),
                ]
            )
        )
        routes.extend(
            (assignment.referee_id.user_id.id, "official")
            for assignment in officials
            if assignment.referee_id.user_id.active
        )
        return routes + self._organiser_routes(day.edition_id)

    def _communication_presentation(self, model, record_id, kind, user):
        allowed = {
            "schedule_change": "federation.matchday",
            "official_response": "federation.match.referee",
            "document_returned": "federation.player.parental.approval",
            "due_soon": "federation.operation.task",
            "delivery_failure": "federation.communication.delivery",
        }
        if allowed.get(kind) != model or not user.active:
            raise AccessError(_("Notification source is unavailable."))
        source = self.env[model].sudo().browse(record_id).exists()
        if not source:
            raise AccessError(_("Notification source no longer exists."))
        source.ensure_one()
        if kind == "schedule_change":
            publication = source.current_publication_id
            if (
                not publication
                or publication.state != "live"
                or user.id not in merge_roles(self._day_routes(source))
            ):
                raise AccessError(
                    _("You no longer participate in this published match day.")
                )
            venue = source.venue_id
            address = ", ".join(
                part
                for part in [
                    venue.street,
                    venue.street2,
                    " ".join(part for part in [venue.zip, venue.city] if part),
                    venue.country_id.name,
                ]
                if part
            )
            location = (
                "%s (%s)" % (venue.display_name, address)
                if address
                else venue.display_name
            )
            courts = (
                self.env["federation.playing.area"]
                .sudo()
                .browse(
                    [
                        row.get("court_id")
                        for row in publication.assignment_snapshot or []
                        if row.get("court_id")
                    ]
                )
                .exists()
            )
            detail = _(
                "Current venue: %(venue)s. Courts: %(courts)s. Open the current published schedule before travelling.",
                venue=location,
                courts=", ".join(courts.mapped("display_name")),
            )
            return {
                "title": _("Published schedule changed"),
                "detail": detail,
                "next_action": _("Check the current venue and match times"),
                "owner": _("Affected participant"),
                "url": "/my/notifications/schedule/%s" % source.id,
                "task_state": _("Review required"),
            }
        if kind == "official_response":
            edition = source.match_id._competition_workflow_edition()
            organiser = user.id in merge_roles(self._organiser_routes(edition))
            own = source.referee_id.user_id == user
            if not own and not organiser:
                raise AccessError(
                    _("You do not own this assignment or its coverage responsibility.")
                )
            if own:
                source._portal_assert_access(user=user)
                url = "/my/referee-assignments/%s" % source.id
            else:
                source.with_user(user).check_access("read")
                url = "/odoo/federation.match/%s" % source.match_id.id
            replacements = (
                self.env["federation.match.referee"]
                .sudo()
                .search(
                    [
                        ("match_id", "=", source.match_id.id),
                        ("role", "=", source.role),
                        ("publication_id", "=", source.publication_id.id),
                        ("state", "=", "confirmed"),
                    ]
                )
            )
            gap = source.state == "cancelled" and not replacements
            return {
                "title": _("Official coverage update"),
                "detail": (
                    _("Assignment declined or cancelled. Arrange replacement coverage.")
                    if gap
                    else _("Inspect the current assignment and confirmed coverage.")
                ),
                "next_action": (
                    _("Arrange replacement official") if gap else _("Review assignment")
                ),
                "owner": _("Competition organiser") if gap else _("Assigned official"),
                "url": url,
                "task_state": (
                    _("Coverage gap")
                    if gap
                    else (
                        _("Completed")
                        if replacements or source.state in ("confirmed", "completed")
                        else _("Response required")
                    )
                ),
                "complete": bool(replacements)
                or source.state in ("confirmed", "completed"),
            }
        if kind == "document_returned":
            clubs = (
                self.env["federation.club.representative"]
                .sudo()
                ._get_clubs_for_user(user=user)
            )
            if source.player_id.club_id not in clubs:
                raise AccessError(_("You no longer represent this player's club."))
            replacement = source.replacement_ids.sorted("id", reverse=True)[:1]
            completed = source.state == "verified" or bool(
                replacement and replacement.state == "verified"
            )
            waiting = bool(replacement and replacement.state == "draft")
            return {
                "title": _("Document correction requested"),
                "detail": source.review_note
                or _("Open the document to inspect the correction requested."),
                "next_action": (
                    _("Wait for federation review")
                    if waiting
                    else (
                        _("Inspect verified replacement")
                        if completed
                        else (
                            _("Upload corrected evidence")
                            if source.state == "replacement_requested"
                            else _("Inspect current document status")
                        )
                    )
                ),
                "owner": _("Submitting club representative"),
                "url": "/my/players/%s/parental-approvals" % source.player_id.id,
                "task_state": (
                    _("Completed")
                    if completed
                    else (
                        _("Waiting for federation review")
                        if waiting
                        else (
                            _("Correction required")
                            if source.state == "replacement_requested"
                            else source.state
                        )
                    )
                ),
                "complete": completed,
            }
        if kind == "due_soon":
            if source.audience == "manager":
                if not user.has_group(
                    "sports_federation_base.group_federation_manager"
                ):
                    raise AccessError(_("Manager work is restricted."))
                source.with_user(user).check_access("read")
            else:
                self.env["federation.portal.privilege"].portal_assert_in_domain(
                    source,
                    source._portal_get_domain(user=user),
                    _("Task is outside your current scope."),
                    user=user,
                )
            source = source.with_context(journey_viewer_id=user.id)
            if source.journey_status == "unavailable":
                raise AccessError(
                    _("Task source is unavailable with your current permissions.")
                )
            return {
                "title": source.name,
                "detail": source.blocking_reason
                or _("Review the deadline and next action."),
                "next_action": source.next_step or _("Open task"),
                "owner": (
                    source.assigned_user_id.display_name or _("Responsible club")
                    if source.audience == "club"
                    else _("Federation manager")
                ),
                "url": source.journey_url,
                "deadline": source.deadline,
                "task_state": (
                    _("Complete")
                    if (source.state == "done" or source.journey_status == "completed")
                    else (
                        _("Waiting for review")
                        if source.journey_status == "waiting"
                        else _("Action needed")
                    )
                ),
                "complete": (
                    source.state == "done" or source.journey_status == "completed"
                ),
                "actionable": source.state != "done"
                and source.journey_status == "actionable",
            }
        if not user.has_group("sports_federation_base.group_federation_manager"):
            raise AccessError(_("Delivery recovery is restricted to managers."))
        return {
            "title": _("Failed delivery needs recovery"),
            "detail": _(
                "Inspect this delivery and correct the contact or mail configuration. Do not repeat the business action."
            ),
            "next_action": _("Recover delivery"),
            "owner": _("Federation manager"),
            "url": "/odoo/federation.communication.delivery/%s" % source.id,
            "task_state": source.state,
        }

    @notification_effect(fallback_model="federation.communication.receipt")
    def _publish_action(
        self, source, kind, event_key, routes, urgent=False, occurred_on=None
    ):
        source.ensure_one()
        receipts = self.env["federation.communication.receipt"].sudo()
        result = receipts.browse()
        for user_id, roles in merge_roles(routes).items():
            user = self.env["res.users"].sudo().browse(user_id).exists()
            if not user or not user.active:
                continue
            try:
                self._communication_presentation(source._name, source.id, kind, user)
            except AccessError:
                continue
            key = identity(event_key, user_id)
            _lock(self.env, key)
            receipt = receipts.search(
                [("event_key", "=", event_key), ("recipient_id", "=", user_id)], limit=1
            )
            if not receipt:
                receipt = receipts.create(
                    {
                        "name": dict(KIND_SELECTION)[kind],
                        "event_key": event_key,
                        "recipient_id": user_id,
                        "kind": kind,
                        "target_model": source._name,
                        "target_res_id": source.id,
                        "roles": ", ".join(roles),
                        "urgent": urgent,
                        "occurred_on": occurred_on or fields.Datetime.now(),
                    }
                )
                mode = self.env["federation.communication.preference"]._mode_for(
                    user, kind
                )
                if mode in ("immediate", "inbox"):
                    self.env["federation.communication.delivery"].sudo().create(
                        {
                            "name": _("Federation notification"),
                            "delivery_key": key,
                            "recipient_id": user_id,
                            "receipt_ids": [(6, 0, receipt.ids)],
                            "state": "pending" if mode == "immediate" else "suppressed",
                        }
                    )
            result |= receipt
        return result

    @api.model
    def _cron_action_digests(self):
        now = fields.Datetime.now()
        users = self.env["res.users"].sudo().search([("active", "=", True)])
        tasks = self.env["federation.operation.task"].sudo()
        managers = users.filtered(
            lambda user: user.has_group(
                "sports_federation_base.group_federation_manager"
            )
        )
        manager_refresh_ok = True
        if managers:
            refresh = self._run_notification_effect(
                lambda: tasks.sync_for_user(user=managers[:1]),
                name="Manager task refresh",
            )
            manager_refresh_ok = refresh._name != "federation.notification.log"
        preferences = (
            self.env["federation.communication.preference"]
            .sudo()
            .search(
                [
                    ("user_id", "in", users.ids),
                ]
            )
        )
        modes = {(row.user_id.id, row.kind): row.mode for row in preferences}
        service = self.with_context(notification_preference_modes=modes)
        for user in users:
            if user in managers and not manager_refresh_ok:
                continue
            service._run_notification_effect(
                lambda user=user: service._digest_for_user(user, now, tasks),
                name="Participant digest",
            )
        return True

    def _digest_for_user(self, user, now, tasks):
        # Refresh only accounts with a current club/team or manager responsibility.
        club = bool(tasks._portal_club_ids(user))
        manager = user.has_group("sports_federation_base.group_federation_manager")
        if club or manager:
            if not manager:
                tasks.sync_for_user(user=user)
            domain = [
                ("state", "!=", "done"),
                ("deadline", ">", now),
                ("deadline", "<=", now + timedelta(days=7)),
            ]
            scope = tasks._portal_get_domain(user=user)
            if manager and club:
                domain = list(
                    Domain.AND(
                        [domain, Domain.OR([scope, [("audience", "=", "manager")]])]
                    )
                )
            else:
                domain += [("audience", "=", "manager")] if manager else scope
            for task in tasks.search(domain):
                try:
                    info = self._communication_presentation(
                        task._name, task.id, "due_soon", user
                    )
                except AccessError:
                    continue
                if not info.get("actionable") or (
                    task.assigned_user_id and task.assigned_user_id != user
                ):
                    continue
                day = fields.Date.context_today(user.with_context(tz=user.tz or "UTC"))
                self._publish_action(
                    task,
                    "due_soon",
                    "due:%s:%s:%s" % (task.id, day, task.deadline),
                    [(user.id, "manager" if task.audience == "manager" else "club")],
                )
        local = fields.Datetime.context_timestamp(
            user.with_context(tz=user.tz or "UTC"), now
        )
        if local.hour < 8:
            return
        key = "digest:%s:%s" % (user.id, local.date())
        _lock(self.env, key)
        deliveries = self.env["federation.communication.delivery"].sudo()
        if deliveries.search_count([("delivery_key", "=", key)]):
            return
        candidates = (
            self.env["federation.communication.receipt"]
            .sudo()
            .search(
                [
                    ("recipient_id", "=", user.id),
                    ("delivery_ids", "=", False),
                    ("acknowledged_on", "=", False),
                    ("superseded_on", "=", False),
                ]
            )
        )
        selected = candidates.browse()
        seen_sources = set()
        for receipt in candidates:
            try:
                info = receipt._presentation(user)
                if self.env["federation.communication.preference"]._mode_for(
                    user, receipt.kind
                ) == "digest" and not info.get("complete", False):
                    source_key = (
                        receipt.kind,
                        receipt.target_model,
                        receipt.target_res_id,
                    )
                    if source_key in seen_sources:
                        receipt.write({"superseded_on": now})
                        continue
                    seen_sources.add(source_key)
                    selected |= receipt
            except AccessError:
                continue
        if selected:
            deliveries.create(
                {
                    "name": _("Daily federation work digest"),
                    "delivery_key": key,
                    "recipient_id": user.id,
                    "receipt_ids": [(6, 0, selected.ids)],
                }
            )
        return True

    def send_referee_assigned(self, match_officiating):
        user = match_officiating.referee_id.user_id
        if (
            not user
            or not match_officiating.fixture_id
            or not match_officiating.publication_id
        ):
            return super().send_referee_assigned(match_officiating)
        return self._publish_action(
            match_officiating,
            "official_response",
            "assigned:%s:%s" % (match_officiating.id, match_officiating.assigned_on),
            [(user.id, "official")] if user else [],
            urgent=True,
        )
