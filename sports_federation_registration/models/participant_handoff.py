import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_HANDOFF = object()


def governed(records):
    return records.with_context(participant_handoff_token=_HANDOFF)


def authorized(env):
    return env.context.get("participant_handoff_token") is _HANDOFF


class RegistrationHandoff(models.Model):
    _inherit = "federation.registration.window"

    finalized_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    finalized_on = fields.Datetime(readonly=True, copy=False)
    finalized_digest = fields.Char(readonly=True, copy=False)

    def _lock_handoff(self):
        self.ensure_one()
        self.check_access("write")
        self.env["federation.competition.role.assignment"].assert_role(
            self.edition_id,
            "registration_manager",
            "competition_director",
        )
        # Division lock serializes separate windows targeting the same playing group.
        self.env.cr.execute(
            "SELECT id FROM federation_tournament WHERE id = %s FOR UPDATE",
            [self.division_id.id],
        )
        self.env.cr.execute(
            "SELECT id FROM federation_registration_window WHERE id = %s FOR UPDATE",
            [self.id],
        )
        self.invalidate_recordset()
        self.entry_ids.invalidate_recordset()

    def _entry_digest(self):
        self.ensure_one()
        rows = [
            (entry.id, entry.team_id.id, entry.seed, entry.state)
            for entry in self.entry_ids.sorted("id")
        ]
        return hashlib.sha256(json.dumps(rows).encode()).hexdigest()

    def action_finalize(self, expected_digest=None):
        for window in self:
            window._lock_handoff()
            if (
                expected_digest is not None
                and expected_digest != window._entry_digest()
            ):
                raise ValidationError(
                    _("Entries changed after review. Refresh the team list.")
                )
            if (
                window.state == "finalized"
                and window.participant_set_id.state == "finalized"
            ):
                continue
            with self.env.cr.savepoint():
                super(RegistrationHandoff, governed(window)).action_finalize()
        return True

    def _materialize_participant_set(self, approved_entries):
        self._lock_handoff()
        if any(
            entry.window_id != self or entry.state != "approved"
            for entry in approved_entries
        ):
            raise ValidationError(
                _("Only approved entries of this registration window can be finalized.")
            )
        if self.division_id.edition_id != self.edition_id:
            raise ValidationError(
                _("The registration division must belong to its edition.")
            )
        other = (
            self.env["federation.registration.window"]
            .sudo()
            .search(
                [
                    ("division_id", "=", self.division_id.id),
                    ("id", "!=", self.id),
                    ("state", "=", "finalized"),
                    ("participant_set_id.state", "=", "finalized"),
                ],
                limit=1,
            )
        )
        if other:
            raise ValidationError(
                _(
                    "Another window owns this division's finalized teams. Amend that window."
                )
            )
        for entry in approved_entries:
            if not entry.team_id.active:
                raise ValidationError(_("Inactive teams cannot be finalized."))
            error = self.division_id.get_team_eligibility_error(entry.team_id)
            if error:
                raise ValidationError(error)
        with self.env.cr.savepoint():
            pset = super(
                RegistrationHandoff, governed(self)
            )._materialize_participant_set(approved_entries)
            governed(self).write(
                {
                    "finalized_by_id": self.env.user.id,
                    "finalized_on": fields.Datetime.now(),
                    "finalized_digest": self._entry_digest(),
                }
            )
            return pset

    def _sync_tournament_participants(self, participant_set, skip_ineligible=False):
        result = super(
            RegistrationHandoff, governed(self)
        )._sync_tournament_participants(
            participant_set,
            skip_ineligible=skip_ineligible,
        )
        entries = {
            entry.team_id.id: entry
            for entry in self.entry_ids.filtered(lambda e: e.state == "approved")
        }
        for participant in (
            self.env["federation.tournament.participant"]
            .sudo()
            .search(
                [
                    ("tournament_id", "=", participant_set.division_id.id),
                    ("state", "=", "confirmed"),
                ]
            )
        ):
            entry = entries.get(participant.team_id.id)
            if entry:
                governed(participant).write(
                    {
                        "source_entry_id": entry.id,
                        "source_participant_set_id": participant_set.id,
                    }
                )
        return result

    def materialize_direct_team_selection(self, teams):
        self._lock_handoff()
        current = self.participant_set_id
        if (
            current
            and set(current.line_ids.team_id.ids) != set(teams.ids)
            and not authorized(self.env)
        ):
            raise ValidationError(
                _(
                    "Use Amend finalized teams with a reason, rather than editing finalized entries."
                )
            )
        with self.env.cr.savepoint():
            return super(
                RegistrationHandoff, governed(self)
            ).materialize_direct_team_selection(teams)

    def amend_finalized_teams(self, team_ids, reason, expected_participant_set_id):
        self._lock_handoff()
        if not (reason or "").strip():
            raise ValidationError(_("An amendment reason is required."))
        if (
            self.state != "finalized"
            or self.participant_set_id.id != expected_participant_set_id
        ):
            raise ValidationError(
                _("The finalized team list changed. Refresh before amending.")
            )
        ids = set(int(value) for value in team_ids)
        teams = self.env["federation.team"].browse(sorted(ids)).exists()
        if set(teams.ids) != ids:
            raise ValidationError(_("A selected team no longer exists."))
        # Existing command rejects changes once a format depends on this snapshot.
        with self.env.cr.savepoint():
            old = self.participant_set_id
            new = governed(self).materialize_direct_team_selection(teams)
            if new != old:
                self.message_post(
                    body=_("Team list amended: %(reason)s", reason=reason.strip())
                )
                self.env["federation.competition.event"].emit(
                    new,
                    "participant_set_amended",
                    {
                        "previous_set_id": old.id,
                        "reason": reason.strip(),
                        "removed_team_ids": sorted(set(old.line_ids.team_id.ids) - ids),
                        "added_team_ids": sorted(ids - set(old.line_ids.team_id.ids)),
                    },
                )
            return new

    def write(self, vals):
        if not authorized(self.env):
            protected = {
                "participant_set_id",
                "finalized_by_id",
                "finalized_on",
                "finalized_digest",
            }
            if protected.intersection(vals):
                raise ValidationError(_("Finalization metadata is command-owned."))
            if any(window.state == "finalized" for window in self) and {
                "state",
                "edition_id",
                "division_id",
            }.intersection(vals):
                raise ValidationError(
                    _(
                        "Finalized registration cannot be reopened or reinterpreted directly."
                    )
                )
        return super().write(vals)

    def action_review_finalization(self):
        self.ensure_one()
        self._lock_handoff()
        wizard = self.env["federation.teams.handoff.wizard"].create(
            {
                "window_id": self.id,
                "expected_digest": self._entry_digest(),
                "expected_participant_set_id": self.participant_set_id.id,
                "amendment": self.state == "finalized",
                "team_ids": [
                    fields.Command.set(self.participant_set_id.line_ids.team_id.ids)
                ],
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }


def lock_entry_windows(windows):
    windows = windows.exists().sorted("id")
    if not windows:
        return
    windows.env.cr.execute(
        "SELECT id FROM federation_tournament WHERE id IN %s ORDER BY id FOR UPDATE",
        [tuple(sorted(set(windows.division_id.ids)))],
    )
    windows.env.cr.execute(
        "SELECT id FROM federation_registration_window WHERE id IN %s ORDER BY id FOR UPDATE",
        [tuple(windows.ids)],
    )
    windows.invalidate_recordset()


class FinalizedEntryGuard(models.Model):
    _inherit = "federation.competition.entry"

    @api.model_create_multi
    def create(self, vals_list):
        if not authorized(self.env):
            self.check_access("create")
            ids = [
                vals.get("window_id") or self.env.context.get("default_window_id")
                for vals in vals_list
            ]
            lock_entry_windows(
                self.env["federation.registration.window"].browse([i for i in ids if i])
            )
            if (
                self.env["federation.registration.window"]
                .browse([i for i in ids if i])
                .filtered(lambda w: w.state == "finalized")
            ):
                raise ValidationError(
                    _("Use the finalized team amendment command to add entries.")
                )
        return super().create(vals_list)

    def write(self, vals):
        if not authorized(self.env) and {
            "team_id",
            "window_id",
            "seed",
            "state",
        }.intersection(vals):
            self.check_access("write")
            lock_entry_windows(
                self.window_id
                | self.env["federation.registration.window"].browse(
                    vals.get("window_id")
                )
            )
            self.invalidate_recordset()
            target = self.env["federation.registration.window"].browse(
                vals.get("window_id")
            )
            if (
                self.filtered(lambda entry: entry.window_id.state == "finalized")
                or target.state == "finalized"
            ):
                raise ValidationError(
                    _(
                        "Finalized entries are historical applications. Use a team amendment."
                    )
                )
        return super().write(vals)

    def unlink(self):
        self.check_access("unlink")
        lock_entry_windows(self.window_id)
        if self.filtered(lambda entry: entry.window_id.state == "finalized"):
            raise ValidationError(_("Finalized entry history cannot be deleted."))
        return super().unlink()


class ManagedParticipant(models.Model):
    _inherit = "federation.tournament.participant"

    source_entry_id = fields.Many2one(
        "federation.competition.entry", readonly=True, copy=False, ondelete="restrict"
    )
    source_participant_set_id = fields.Many2one(
        "federation.participant.set", readonly=True, copy=False, ondelete="restrict"
    )

    @api.model_create_multi
    def create(self, vals_list):
        if not authorized(self.env):
            ids = [
                v.get("tournament_id") or self.env.context.get("default_tournament_id")
                for v in vals_list
            ]
            if any(
                v.get("source_entry_id") or v.get("source_participant_set_id")
                for v in vals_list
            ):
                raise ValidationError(
                    _("Participation source links are command-owned.")
                )
            if (
                self.env["federation.registration.window"]
                .sudo()
                .search_count(
                    [
                        ("division_id", "in", [i for i in ids if i]),
                        ("state", "=", "finalized"),
                    ]
                )
            ):
                raise ValidationError(
                    _(
                        "Add accepted teams through the finalized team amendment command."
                    )
                )
        return super().create(vals_list)

    def write(self, vals):
        if not authorized(self.env) and {
            "team_id",
            "tournament_id",
            "state",
            "seed",
            "source_entry_id",
            "source_participant_set_id",
        }.intersection(vals):
            if self.filtered("source_entry_id") or {
                "source_entry_id",
                "source_participant_set_id",
            }.intersection(vals):
                raise ValidationError(
                    _(
                        "Managed participants follow the finalized team list. Use a team amendment."
                    )
                )
        return super().write(vals)

    def unlink(self):
        if self.filtered("source_entry_id"):
            raise ValidationError(_("Managed participation history cannot be deleted."))
        return super().unlink()


class ParticipantSnapshotGuard(models.Model):
    _inherit = "federation.participant.set"

    def write(self, vals):
        if not authorized(self.env) and self.filtered(lambda row: row.state != "draft"):
            raise ValidationError(_("Finalized participant snapshots are immutable."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda row: row.state != "draft"):
            raise ValidationError(_("Retain finalized participant snapshots."))
        return super().unlink()


class ParticipantSnapshotLineGuard(models.Model):
    _inherit = "federation.participant.set.line"

    @api.model_create_multi
    def create(self, vals_list):
        if not authorized(self.env):
            ids = [
                v.get("participant_set_id")
                or self.env.context.get("default_participant_set_id")
                for v in vals_list
            ]
            if (
                self.env["federation.participant.set"]
                .browse([i for i in ids if i])
                .filtered(lambda row: row.state != "draft")
            ):
                raise ValidationError(_("Finalized snapshot lines are command-owned."))
        return super().create(vals_list)

    def write(self, vals):
        target = self.env["federation.participant.set"].browse(
            vals.get("participant_set_id")
        )
        if not authorized(self.env) and (
            self.filtered(lambda row: row.participant_set_id.state != "draft")
            or (target and target.state != "draft")
        ):
            raise ValidationError(_("Finalized snapshot lines are immutable."))
        return super().write(vals)

    def unlink(self):
        if self.filtered(lambda row: row.participant_set_id.state != "draft"):
            raise ValidationError(_("Retain finalized snapshot lines."))
        return super().unlink()


class TeamHandoffWizard(models.TransientModel):
    _name = "federation.teams.handoff.wizard"
    _description = "Review Finalized Teams"

    window_id = fields.Many2one(
        "federation.registration.window", required=True, readonly=True
    )
    expected_digest = fields.Char(required=True, readonly=True)
    expected_participant_set_id = fields.Many2one(
        "federation.participant.set", readonly=True
    )
    amendment = fields.Boolean(readonly=True)
    team_ids = fields.Many2many("federation.team", string="Revised teams")
    reason = fields.Text()
    entry_ids = fields.One2many(related="window_id.entry_ids", readonly=True)

    def action_apply(self):
        self.ensure_one()
        if self.amendment:
            self.window_id.amend_finalized_teams(
                self.team_ids.ids, self.reason, self.expected_participant_set_id.id
            )
        else:
            self.window_id.action_finalize(expected_digest=self.expected_digest)
        return self.window_id.get_formview_action()
