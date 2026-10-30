"""Persisted command contracts. Run on the supported application installation."""
from uuid import uuid4
from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.addons.sports_federation_duty_coverage.tests.common import CoverageFixture


class LiveFixture(CoverageFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.write({"group_ids": [(4, cls.env.ref("sports_federation_matchday.group_matchday_manager").id),
            (4, cls.env.ref("sports_federation_base.group_federation_manager").id)]})
        cls.operator = cls.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Court operator", "login": "court.operator@example.test",
            "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])]})
        cls.access = cls.env["federation.court.access"].create({"matchday_id": cls.matchday.id,
            "court_id": cls.slot.court_id.id, "user_id": cls.operator.id})
        cls.session = cls.env["federation.matchday.session"].create({"matchday_id": cls.matchday.id,
            "publication_id": cls.publication.id, "publication_digest": cls.publication.snapshot_digest})
        cls.matchday.write({"active_session_id": cls.session.id})
        cls.edition.write({"result_verification_required": True, "result_approval_required": True})
        cls.schedule = cls.env["federation.schedule"].create({"name": "Visual test schedule",
            "edition_id": cls.edition.id, "structure_id": cls.publication.schedule_id.structure_id.id,
            "matchday_id": cls.matchday.id})
        cls.env["federation.matchday.allocation"].create({"matchday_id": cls.matchday.id,
            "structure_id": cls.schedule.structure_id.id, "round_number": 1})
        cls.second_slot = cls.env["federation.schedule.slot"].create({"matchday_id": cls.matchday.id,
            "court_id": cls.slot.court_id.id, "start_datetime": "2026-06-15 19:30:00",
            "end_datetime": "2026-06-15 20:00:00"})

@tagged("post_install", "-at_install", "sf_live_workspace", "sf_release_confidence")
class TestLiveCommands(LiveFixture, TransactionCase):
    def setUp(self):
        super().setUp()
        self.commands = self.env["federation.court.commands"].with_user(self.operator)
        self.plan = self.env["federation.visual.planning"]
        self.args = [self.matchday.id, self.slot.court_id.id, self.match.id]

    def open(self):
        return self.commands.open_match(*self.args)

    def command(self, operation="save", payload=None, base=None):
        base = base or self.open()
        return {"key": str(uuid4()), "revision": base["revision"], "operation": operation,
            "payload": payload or {"home": 2, "away": 1}, "signature": base["signature"]}

    def test_scoped_queue(self):
        self.assertIn(self.match.id, [m["id"] for m in self.commands.load(*self.args[:2])["queue"]])

    def test_portal_denied(self):
        with self.assertRaises(AccessError):
            self.env["federation.court.commands"].with_user(self.official_user).load(*self.args[:2])

    def test_wrong_court_denied(self):
        with self.assertRaises(AccessError): self.commands.load(self.matchday.id, 999999)

    def test_unassigned_match_denied(self):
        with self.assertRaises(AccessError): self.commands.open_match(*self.args[:2], self.other_match.id)

    def test_revoked_operator(self):
        self.access.write({"active": False})
        with self.assertRaises(AccessError): self.open()

    def test_closed_session(self):
        self.session.write({"state": "closed"})
        with self.assertRaises(ValidationError): self.open()

    def test_save_is_not_official(self):
        result = self.commands.sync(*self.args, [self.command()])
        self.assertEqual(result["current"]["revision"], 1)
        self.assertEqual(self.match.result_state, "draft")
        self.assertFalse(self.match.include_in_official_standings)

    def test_duplicate_save_replays(self):
        command = self.command()
        first = self.commands.sync(*self.args, [command])
        second = self.commands.sync(*self.args, [command])
        self.assertEqual(first, second)
        self.assertEqual(self.env["federation.court.receipt"].sudo().search_count([("key", "=", command["key"])]), 1)

    def test_key_content_reuse_rejected(self):
        command = self.command()
        self.commands.sync(*self.args, [command])
        command["payload"] = {"home": 4, "away": 1}
        with self.assertRaises(ValidationError): self.commands.sync(*self.args, [command])

    def test_stale_revision_rejected(self):
        base = self.open()
        self.commands.sync(*self.args, [self.command(base=base)])
        with self.assertRaises(ValidationError): self.commands.sync(*self.args, [self.command(base=base)])

    def test_batch_rolls_back(self):
        base = self.open()
        good = self.command(base=base)
        bad = self.command(payload={"home": -1, "away": 0}, base={**base, "revision": 1})
        with self.assertRaises(ValidationError): self.commands.sync(*self.args, [good, bad])
        self.assertEqual(self.open()["revision"], 0)
        self.assertFalse(self.env["federation.court.receipt"].sudo().search([("key", "=", good["key"])]))

    def test_undo_restores_saved_draft(self):
        base = self.open()
        self.commands.sync(*self.args, [self.command(base=base)])
        result = self.commands.sync(*self.args, [self.command("undo")])
        self.assertEqual(result["current"]["payload"], base["payload"])

    def test_submit_replays_once(self):
        command = self.command("submit")
        self.commands.sync(*self.args, [command])
        self.commands.sync(*self.args, [command])
        self.assertEqual(self.match.result_state, "submitted")
        self.assertEqual(self.match.home_score, 2)
        self.assertFalse(self.match.include_in_official_standings)
        with self.assertRaises(ValidationError): self.commands.sync(*self.args, [self.command()])

    def test_interruption_routes_incident(self):
        payload = {"home": 1, "away": 0, "outcome": "interrupted", "reason": "Court unavailable"}
        self.commands.sync(*self.args, [self.command(payload=payload)])
        self.assertTrue(self.env["federation.matchday.incident"].search([("matchday_id", "=", self.matchday.id)]))
        with self.assertRaises(ValidationError): self.commands.sync(*self.args, [self.command("submit", payload)])

    def test_external_result_change_requires_reconciliation(self):
        base = self.open()
        self.match.write({"home_score": 5})
        with self.assertRaises(ValidationError): self.commands.sync(*self.args, [self.command(base=base)])
        result = self.commands.reconcile(*self.args, base["revision"], "Coordinator checked the source sheet")
        self.assertEqual(result["revision"], 1)

    def test_capture_raw_sudo_write_denied(self):
        self.open()
        capture = self.env["federation.court.capture"].sudo().search([("match_id", "=", self.match.id)])
        with self.assertRaises(AccessError): capture.write({"submitted": True})

    def test_visual_preview_is_nonmutating(self):
        fid = self.schedule.available_fixture_ids[0].id
        revision = self.schedule.revision
        self.plan.preview(self.schedule.id, "move", fid, self.slot.id)
        self.assertEqual(self.schedule.revision, revision)
        self.assertFalse(self.schedule.assignment_ids)

    def test_visual_apply_exact_preview_and_replay(self):
        fid = self.schedule.available_fixture_ids[0].id
        preview = self.plan.preview(self.schedule.id, "move", fid, self.slot.id)
        self.plan.apply(preview["id"], "Pin court")
        self.plan.apply(preview["id"], "Pin court")
        self.assertEqual(len(self.schedule.assignment_ids), 1)
        self.assertEqual(self.schedule.assignment_ids.method, "manual")
        self.assertEqual(self.schedule.revision, 1)

    def test_visual_stale_constraint_rejected(self):
        fid = self.schedule.available_fixture_ids[0].id
        preview = self.plan.preview(self.schedule.id, "move", fid, self.slot.id)
        self.env["federation.visual.constraint"].create({"schedule_id": self.schedule.id,
            "name": "Hard rest", "kind": "minimum_rest", "minutes": 30})
        with self.assertRaises(ValidationError): self.plan.apply(preview["id"], "Stale")

    def test_visual_hard_constraint_blocks(self):
        self.env["federation.visual.constraint"].create({"schedule_id": self.schedule.id,
            "name": "Court closed", "kind": "court_window", "court_id": self.slot.court_id.id,
            "start": self.slot.start_datetime, "end": self.slot.end_datetime})
        preview = self.plan.preview(self.schedule.id, "move", self.schedule.available_fixture_ids[0].id, self.slot.id)
        self.assertTrue(preview["after"]["validation"]["errors"])
        with self.assertRaises(ValidationError): self.plan.apply(preview["id"], "Cannot apply")

    def test_manual_pin_survives_regeneration(self):
        fid = self.schedule.available_fixture_ids[0].id
        preview = self.plan.preview(self.schedule.id, "move", fid, self.slot.id)
        self.plan.apply(preview["id"], "Pin")
        preview = self.plan.preview(self.schedule.id, "regenerate")
        record = self.env["federation.visual.proposal"].sudo().browse(preview["id"])
        self.assertEqual(record.candidate[str(fid)], self.slot.id)

    def test_published_preview_denied(self):
        with self.assertRaises(ValidationError): self.plan.preview(self.publication.schedule_id.id, "regenerate")

    def test_visual_portal_denied(self):
        with self.assertRaises((AccessError, ValidationError)):
            self.plan.with_user(self.official_user).load(self.schedule.id)

    def test_schedule_replay_content_bound(self):
        commands = self.env["federation.schedule.commands"]
        fid = self.schedule.available_fixture_ids[0].id
        commands.assign(self.schedule.id, fid, self.slot.id, 0, idempotency_key="test-replay")
        with self.assertRaises(ValidationError):
            commands.assign(self.schedule.id, fid, self.second_slot.id, 0, idempotency_key="test-replay")

    def test_dispute_hold_survives_normal_save(self):
        self.commands.sync(*self.args, [self.command(payload={"home": 2, "away": 1,
            "outcome": "disputed", "reason": "Score disagreement"})])
        self.commands.sync(*self.args, [self.command()])
        self.assertTrue(self.open()["review_required"])
        with self.assertRaises(ValidationError): self.commands.sync(*self.args, [self.command("submit")])
