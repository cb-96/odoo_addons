from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..identity_backfill_policy import plan
from ..lifecycle_policy import fingerprint, normal_name
from .lifecycle import command, lock
from .membership import manager


def match_key(first_name, last_name, birth_date):
    """The same key the duplicate guard computes when a player is created."""
    return fingerprint(
        (normal_name(first_name), normal_name(last_name), str(birth_date))
    )


class IdentityCandidate(models.Model):
    """A group of players that look like one person, waiting for a reviewed decision.

    The queue only finds and lists. Merging stays in the reviewed identity
    decision, with its preview, company-scope checks and immutable history.
    """

    _name = "federation.identity.candidate"
    _description = "Possible Duplicate Player Identity"
    _order = "status, detected_on desc, id desc"

    match_key = fields.Char(required=True, readonly=True, index=True)
    player_ids = fields.Many2many(
        "federation.player",
        "federation_identity_candidate_player_rel",
        "candidate_id",
        "player_id",
        readonly=True,
    )
    open_player_count = fields.Integer(
        compute="_compute_open_player_count",
        store=True,
        help="Players of this group that have not been resolved as a duplicate yet.",
    )
    dismissed = fields.Boolean(readonly=True, copy=False)
    status = fields.Selection(
        [
            ("open", "To review"),
            ("dismissed", "Not a duplicate"),
            ("resolved", "Resolved"),
        ],
        compute="_compute_status",
        store=True,
        index=True,
    )
    note = fields.Text()
    detected_on = fields.Datetime(default=fields.Datetime.now, readonly=True)
    decided_on = fields.Datetime(readonly=True)
    decided_by_id = fields.Many2one("res.users", readonly=True)

    _match_key_unique = models.Constraint(
        "unique(match_key)", "A review group already exists for this identity."
    )

    @api.depends("player_ids.family_duplicate_of_id")
    def _compute_open_player_count(self):
        for candidate in self:
            players = candidate.player_ids.sudo()
            candidate.open_player_count = len(
                players.filtered(lambda player: not player.family_duplicate_of_id)
            )

    @api.depends("dismissed", "open_player_count")
    def _compute_status(self):
        for candidate in self:
            if candidate.dismissed:
                candidate.status = "dismissed"
            elif candidate.open_player_count <= 1:
                candidate.status = "resolved"
            else:
                candidate.status = "open"

    # ------------------------------------------------------------------
    # Backfill
    # ------------------------------------------------------------------

    @api.model
    def run_backfill(self, batch=500):
        """Key the safe players and queue the groups that need a human decision."""
        manager(self.env)
        Player = self.env["federation.player"].sudo().with_context(active_test=False)
        players = Player.search(
            [("family_match_key", "=", False), ("family_duplicate_of_id", "=", False)],
            order="id",
            limit=batch,
        )
        lock(players)
        rows = [
            {
                "id": player.id,
                "first_name": player.first_name,
                "last_name": player.last_name,
                "birth_date": player.birth_date,
            }
            for player in players
        ]
        keys = {
            match_key(row["first_name"], row["last_name"], row["birth_date"])
            for row in rows
            if row["birth_date"]
        }
        holders = {}
        if keys:
            for held in Player.search_read(
                [("family_match_key", "in", list(keys))], ["family_match_key"]
            ):
                holders.setdefault(held["family_match_key"], []).append(held["id"])
        result = plan(rows, holders, match_key)
        keyed, candidates = 0, dict(result["candidates"])
        for player_id, key in result["to_key"]:
            try:
                with self.env.cr.savepoint():
                    command(Player.browse(player_id)).write({"family_match_key": key})
                keyed += 1
            except IntegrityError:
                # Someone else took the key meanwhile; that is a duplicate to review.
                holder = Player.search([("family_match_key", "=", key)]).ids
                candidates[key] = sorted({player_id, *holder})
        for key, ids in candidates.items():
            self._upsert_candidate(key, ids)
        return {
            "scanned": len(rows),
            "keyed": keyed,
            "candidates": len(candidates),
            "needs_birth_date": len(result["needs_birth_date"]),
            "more": len(rows) >= batch,
        }

    @api.model
    def _upsert_candidate(self, key, player_ids):
        candidate = self.search([("match_key", "=", key)], limit=1)
        if not candidate:
            return self.create({"match_key": key, "player_ids": [(6, 0, player_ids)]})
        known = set(candidate.player_ids.ids)
        if set(player_ids) <= known:
            return candidate
        values = {"player_ids": [(6, 0, sorted(known | set(player_ids)))]}
        if candidate.dismissed:
            # A new player joined a group that was dismissed: look again.
            values.update(dismissed=False, decided_on=False, decided_by_id=False)
        candidate.write(values)
        return candidate

    def action_run_backfill(self):
        stats = self.run_backfill()
        message = _(
            "%(keyed)s players matched, %(candidates)s possible duplicate groups queued, "
            "%(gap)s players need a birth date.",
            keyed=stats["keyed"],
            candidates=stats["candidates"],
            gap=stats["needs_birth_date"],
        )
        if stats["more"]:
            message += " " + _("More players remain; run the backfill again.")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Identity backfill"),
                "message": message,
                "sticky": False,
            },
        }

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    def action_review(self):
        """Open the reviewed identity merge for the next pair of this group."""
        manager(self.env)
        self.ensure_one()
        players = (
            self.player_ids.sudo()
            .filtered(lambda p: not p.family_duplicate_of_id)
            .sorted("id")
        )
        if len(players) < 2:
            raise ValidationError(_("Nothing left to review: one identity remains."))
        canonical = players.filtered("person_id")[:1] or players[:1]
        duplicate = (players - canonical)[:1]
        review = self.env["federation.identity.review"].create(
            {
                "player_id": canonical.id,
                "person_id": canonical.person_id.id or False,
                "duplicate_player_id": duplicate.id,
            }
        )
        return {
            "type": "ir.actions.act_window",
            "res_model": review._name,
            "res_id": review.id,
            "view_mode": "form",
            "target": "new",
            "name": _("Review identity, preserve history"),
        }

    def action_dismiss(self):
        manager(self.env)
        for candidate in self:
            if not (candidate.note or "").strip():
                raise ValidationError(
                    _("Explain why these players are different people.")
                )
            candidate.write(
                {
                    "dismissed": True,
                    "decided_on": fields.Datetime.now(),
                    "decided_by_id": self.env.uid,
                }
            )
        return True
