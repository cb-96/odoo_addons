"""Permanently delete competitions, including their protected history.

Competition data normally cannot be deleted: published schedules, court
captures, frozen standings, game-day sessions and results are kept as
evidence by ``unlink`` overrides and ``@api.ondelete`` guards.  That protects
real competitions, but leaves test competitions stuck forever.

This command removes a competition and everything that belongs to it, for
system administrators only.  It is deliberately strict about scope:

* it only follows links *into* the competition (records that point at the
  competition, its divisions, matches, game days, schedules, ...);
* master data is never deleted: clubs, teams, players, licences, seasons,
  season registrations, rosters, venues, courts, referees, rule sets and the
  parent competition (the last one only on explicit request, and only when no
  other competition uses it);
* if anything outside federation data or in master data would block the
  deletion, nothing is deleted and the blocker is reported.

The guards are bypassed the same way Odoo bypasses them when a module is
uninstalled: ``BaseModel.unlink`` with the module-uninstall flag.  Chatter,
followers, activities and attachments of the deleted records are removed too.
"""

import logging
from collections import defaultdict

import psycopg2

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError, ValidationError

try:  # Odoo exposes the uninstall flag here; keep the literal as a fallback.
    from odoo.models import MODULE_UNINSTALL_FLAG
except ImportError:  # pragma: no cover
    MODULE_UNINSTALL_FLAG = "_force_unlink"

_logger = logging.getLogger(__name__)

PROTECTED_MODELS = {
    "federation.club",
    "federation.team",
    "federation.player",
    "federation.player.license",
    "federation.season",
    "federation.season.registration",
    "federation.team.roster",
    "federation.team.roster.line",
    "federation.venue",
    "federation.playing.area",
    "federation.referee",
    "federation.rule.set",
    "federation.club.representative",
    "federation.competition",
}


class FederationCompetitionForceDelete(models.AbstractModel):
    _name = "federation.competition.force.delete"
    _description = "Permanent Competition Deletion"

    # ------------------------------------------------------------------
    # Scope
    # ------------------------------------------------------------------

    @api.model
    def _assert_allowed(self):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(
                _("Only system administrators can permanently delete competitions.")
            )

    @api.model
    def _reference_index(self):
        """``{target_model: [(model, field, ondelete, required), ...]}`` for stored many2one."""
        index = defaultdict(list)
        for model_name in self.env.registry:
            Model = self.env[model_name]
            if Model._abstract or not Model._auto:
                continue
            for field in Model._fields.values():
                if field.type == "many2one" and field.store and field.comodel_name:
                    index[field.comodel_name].append(
                        (model_name, field.name, field.ondelete, bool(field.required))
                    )
        return index

    @api.model
    def _is_owned_model(self, model_name):
        return (
            model_name.startswith("federation.") and model_name not in PROTECTED_MODELS
        )

    @api.model
    def collect(self, editions, include_parent=False):
        """Everything that would be deleted, plus blockers.

        Returns ``{"records": {model: set(ids)}, "depth": {model: int},
        "blockers": [str], "parents": recordset}``.
        """
        env = self.env(su=True)
        editions = (
            env["federation.competition.edition"]
            .with_context(active_test=False)
            .browse(editions.ids)
        )
        index = self._reference_index()
        records = defaultdict(set)
        depth = {}
        blockers = []
        records["federation.competition.edition"].update(editions.ids)
        depth["federation.competition.edition"] = 0
        frontier = {"federation.competition.edition": set(editions.ids)}
        level = 0
        while frontier:
            level += 1
            next_frontier = defaultdict(set)
            for target, ids in frontier.items():
                for model_name, field_name, ondelete, required in index.get(target, ()):
                    Model = env[model_name].with_context(active_test=False)
                    found = Model.search([(field_name, "in", list(ids))])
                    new_ids = set(found.ids) - records[model_name]
                    if not new_ids:
                        continue
                    if not self._is_owned_model(model_name):
                        if ondelete == "set null" and not required:
                            continue  # the database clears the link
                        blockers.append(
                            _(
                                "%(count)s %(model)s record(s) depend on it (%(field)s).",
                                count=len(new_ids),
                                model=Model._description or model_name,
                                field=Model._fields[field_name].string,
                            )
                        )
                        continue
                    records[model_name].update(new_ids)
                    depth[model_name] = max(depth.get(model_name, 0), level)
                    next_frontier[model_name].update(new_ids)
            frontier = next_frontier

        parents = env["federation.competition"]
        if include_parent:
            for parent in editions.mapped("competition_id"):
                other_editions = (
                    env["federation.competition.edition"]
                    .with_context(active_test=False)
                    .search_count(
                        [
                            ("competition_id", "=", parent.id),
                            (
                                "id",
                                "not in",
                                list(records["federation.competition.edition"]),
                            ),
                        ]
                    )
                )
                other_divisions = (
                    env["federation.tournament"]
                    .with_context(active_test=False)
                    .search_count(
                        [
                            ("competition_id", "=", parent.id),
                            ("id", "not in", list(records["federation.tournament"])),
                        ]
                    )
                )
                if not other_editions and not other_divisions:
                    parents |= parent
        return {
            "records": records,
            "depth": depth,
            "blockers": blockers,
            "parents": parents,
        }

    @api.model
    def summary(self, scope):
        """Human-readable ``[(label, count)]``, largest first."""
        rows = []
        for model_name, ids in scope["records"].items():
            if not ids:
                continue
            Model = self.env[model_name]
            if Model._transient:
                continue
            rows.append((Model._description or model_name, len(ids)))
        if scope["parents"]:
            rows.append(
                (self.env["federation.competition"]._description, len(scope["parents"]))
            )
        return sorted(rows, key=lambda row: (-row[1], row[0]))

    @api.model
    def warnings(self, scope):
        env = self.env(su=True)
        notes = []
        match_ids = list(scope["records"].get("federation.match", ()))
        if match_ids and "result_state" in env["federation.match"]._fields:
            approved = env["federation.match"].search_count(
                [("id", "in", match_ids), ("result_state", "=", "approved")]
            )
            if approved:
                notes.append(
                    _("%(count)s official (approved) match result(s).", count=approved)
                )
        publication_ids = scope["records"].get("federation.schedule.publication", ())
        if publication_ids:
            notes.append(
                _("%(count)s published schedule(s).", count=len(publication_ids))
            )
        return notes

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    @api.model
    def _break_internal_links(self, env, records):
        """Clear optional restrict links between records that will all be deleted.

        This removes ordering problems and cycles (for example a game day
        pointing at its current publication, which points back at the
        schedule of that game day).
        """
        cr = env.cr
        for model_name, ids in records.items():
            Model = env[model_name]
            if not ids:
                continue
            for field in Model._fields.values():
                if (
                    field.type == "many2one"
                    and field.store
                    and not field.required
                    and field.ondelete == "restrict"
                    and records.get(field.comodel_name)
                ):
                    cr.execute(
                        'UPDATE "%s" SET "%s" = NULL WHERE id IN %%s AND "%s" IN %%s'
                        % (Model._table, field.name, field.name),
                        (tuple(ids), tuple(records[field.comodel_name])),
                    )
        env.invalidate_all()

    @api.model
    def _purge(self, Model, ids):
        records = Model.browse(list(ids)).exists()
        if not records:
            return
        env = Model.env
        if "message_ids" in records._fields:
            env["mail.message"].search(
                [("model", "=", records._name), ("res_id", "in", records.ids)]
            ).unlink()
            env["mail.followers"].search(
                [("res_model", "=", records._name), ("res_id", "in", records.ids)]
            ).unlink()
        if "activity_ids" in records._fields:
            env["mail.activity"].search(
                [("res_model", "=", records._name), ("res_id", "in", records.ids)]
            ).unlink()
        env["ir.attachment"].search(
            [("res_model", "=", records._name), ("res_id", "in", records.ids)]
        ).unlink()
        # Same path as module uninstallation: skips unlink overrides and
        # evidence guards declared with @api.ondelete(at_uninstall=False).
        models.BaseModel.unlink(records)

    @api.model
    def execute(self, editions, include_parent=False):
        self._assert_allowed()
        editions = editions.exists()
        if not editions:
            raise UserError(_("Select at least one competition."))
        published = editions.filtered(
            lambda edition: "website_published" in edition._fields
            and edition.website_published
        )
        if published:
            raise UserError(
                _(
                    "Unpublish these competitions from the website first: %(names)s",
                    names=", ".join(published.mapped("display_name")),
                )
            )
        scope = self.collect(editions, include_parent=include_parent)
        if scope["blockers"]:
            raise UserError(
                _(
                    "Nothing was deleted because other data depends on it:\n- %(items)s",
                    items="\n- ".join(scope["blockers"]),
                )
            )
        names = editions.mapped("display_name")
        summary = self.summary(scope)
        env = self.env(
            su=True,
            context=dict(
                self.env.context,
                active_test=False,
                tracking_disable=True,
                **{MODULE_UNINSTALL_FLAG: True}
            ),
        )
        records = {name: set(ids) for name, ids in scope["records"].items() if ids}
        self._break_internal_links(env, records)

        order = sorted(records, key=lambda name: (-scope["depth"].get(name, 0), name))
        remaining = list(order)
        errors = {}
        for _attempt in range(len(order) + 2):
            progressed = False
            for model_name in list(remaining):
                try:
                    with env.cr.savepoint():
                        self._purge(env[model_name], records[model_name])
                    remaining.remove(model_name)
                    progressed = True
                except (psycopg2.Error, UserError, ValidationError) as error:
                    errors[model_name] = str(error).splitlines()[0]
            if not remaining or not progressed:
                break
        if remaining:
            raise UserError(
                _(
                    "The competition could not be deleted completely:\n- %(items)s",
                    items="\n- ".join(
                        "%s: %s" % (env[name]._description, errors.get(name, ""))
                        for name in remaining
                    ),
                )
            )
        if scope["parents"]:
            try:
                with env.cr.savepoint():
                    self._purge(env["federation.competition"], scope["parents"].ids)
            except (psycopg2.Error, UserError, ValidationError):
                _logger.info("Parent competition kept: still referenced.")

        message = _(
            "%(user)s permanently deleted %(names)s: %(details)s",
            user=self.env.user.display_name,
            names=", ".join(names),
            details=", ".join("%s %s" % (count, label) for label, count in summary),
        )
        _logger.warning(message)
        env["ir.logging"].create(
            {
                "name": "sports_federation.force_delete",
                "type": "server",
                "dbname": env.cr.dbname,
                "level": "WARNING",
                "message": message,
                "path": __name__,
                "func": "execute",
                "line": "0",
            }
        )
        return summary
