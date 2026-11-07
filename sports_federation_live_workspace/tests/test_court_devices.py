"""Offline court scoring: per-match rights, device tokens, sync and approval.

Run on the supported application installation.
"""

from uuid import uuid4

from freezegun import freeze_time

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import HttpCase, TransactionCase, tagged

from .test_commands import LiveFixture

GAME_DAY = "2026-06-15 16:00:00"


class DeviceFixture(LiveFixture):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Referee rights start when the assignment is confirmed.
        cls.assignment.write({"state": "confirmed"})
        cls.service = cls.env["federation.court.device.service"]
        cls.Commands = cls.env["federation.court.commands"]
        cls.approver = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Tournament manager",
                    "login": "tournament.manager@example.test",
                    "group_ids": [
                        (
                            6,
                            0,
                            [
                                cls.env.ref("base.group_user").id,
                                cls.env.ref(
                                    "sports_federation_base.group_federation_manager"
                                ).id,
                                cls.env.ref(
                                    "sports_federation_matchday.group_matchday_manager"
                                ).id,
                                cls.env.ref(
                                    "sports_federation_result_control.group_result_approver"
                                ).id,
                            ],
                        )
                    ],
                }
            )
        )

    def prepare(self, user=None, label="Phone"):
        user = user or self.official_user
        code = self.service.with_user(user)._prepare_device(self.matchday.id, label)
        device, token = self.service._activate(code)
        return self.service.with_user(user), device, token

    def command(self, operation="save", payload=None, revision=0, **extra):
        value = {
            "key": str(uuid4()),
            "revision": revision,
            "operation": operation,
            "payload": payload or {"home": 2, "away": 1},
            "signature": self.Commands._device_signature(self.match),
        }
        value.update(extra)
        return value


@tagged("post_install", "-at_install", "sf_live_workspace", "sf_release_confidence")
class TestCourtDevices(DeviceFixture, TransactionCase):
    @freeze_time(GAME_DAY)
    def test_head_referee_scores_and_result_waits_for_manager(self):
        # Even when the competition does not require review, court results do.
        self.edition.write(
            {"result_verification_required": False, "result_approval_required": False}
        )
        service, device, token = self.prepare()
        self.assertEqual(self.service._authenticate(token), device)
        pack = service._pack(device)
        self.assertEqual([row["id"] for row in pack["matches"]], [self.match.id])
        self.assertEqual(pack["matches"][0]["source"], "head_referee")
        service._sync(device, self.match.id, [self.command()])
        result = service._sync(
            device,
            self.match.id,
            [self.command("submit", revision=1, confirmation={"method": "self"})],
        )
        self.assertTrue(result["current"]["submitted"])
        self.assertEqual(self.match.result_state, "submitted")
        capture = self.match.court_capture_ids
        self.assertEqual(capture.device_id, device)
        self.assertEqual(capture.scorer_source, "head_referee")
        self.assertEqual(capture.referee_confirmation, "head_referee")
        self.assertEqual(set(capture.receipt_ids.mapped("device_id")), {device})

    @freeze_time(GAME_DAY)
    def test_pack_lists_only_matches_the_user_may_score(self):
        _service, device, _token = self.prepare()
        pack = self.service._pack(device)
        self.assertNotIn(self.other_match.id, [row["id"] for row in pack["matches"]])
        with self.assertRaises(AccessError):
            self.service.with_user(self.official_user)._sync(
                device, self.other_match.id, [self.command()]
            )

    @freeze_time(GAME_DAY)
    def test_unconfirmed_or_cancelled_assignment_gives_no_rights(self):
        self.assignment.write({"state": "draft"})
        with self.assertRaises(AccessError):
            self.prepare()
        self.assignment.write({"state": "confirmed"})
        service, device, _token = self.prepare()
        self.assignment.write({"state": "cancelled"})
        with self.assertRaises(AccessError):
            service._sync(device, self.match.id, [self.command()])

    @freeze_time(GAME_DAY)
    def test_code_is_single_use_and_token_revocable(self):
        code = self.service.with_user(self.official_user)._prepare_device(
            self.matchday.id
        )
        device, token = self.service._activate(code)
        with self.assertRaises(AccessError):
            self.service._activate(code)
        self.service.with_user(self.official_user)._revoke_own(device.id)
        with self.assertRaises(AccessError):
            self.service._authenticate(token)

    @freeze_time(GAME_DAY)
    def test_token_expires_after_the_game_day(self):
        _service, device, token = self.prepare()
        with freeze_time("2026-06-18 12:00:00"):
            with self.assertRaises(AccessError):
                self.service._authenticate(token)
        self.assertEqual(device.state, "expired")

    @freeze_time(GAME_DAY)
    def test_second_phone_needs_explicit_takeover(self):
        service, first, _token = self.prepare(label="First")
        service._sync(first, self.match.id, [self.command()])
        _service, second, _token2 = self.prepare(label="Second")
        with self.assertRaises(ValidationError):
            service._sync(second, self.match.id, [self.command(revision=1)])
        current = service._claim(second, self.match.id)
        self.assertTrue(current["this_device"])
        service._sync(second, self.match.id, [self.command(revision=1)])
        with self.assertRaises(ValidationError):
            service._sync(first, self.match.id, [self.command(revision=2)])

    @freeze_time(GAME_DAY)
    def test_scoring_rule_change_turns_queued_commands_into_conflict(self):
        service, device, _token = self.prepare()
        stale = self.command()
        self.edition.write({"court_set_win_points": 2, "court_set_draw_points": 1})
        with self.assertRaises(ValidationError):
            service._sync(device, self.match.id, [stale])

    @freeze_time(GAME_DAY)
    def test_assistant_scores_with_head_referee_pin(self):
        self.env["federation.match.referee"].create(
            {
                "match_id": self.match.id,
                "referee_id": self.other_referee.id,
                "role": "assistant_1",
                "state": "confirmed",
            }
        )
        self.referee._set_court_pin("4821")
        service, device, _token = self.prepare(self.other_user)
        service._sync(device, self.match.id, [self.command()])
        service._sync(
            device,
            self.match.id,
            [
                self.command(
                    "submit",
                    revision=1,
                    confirmation={"method": "pin", "pin": "4821"},
                )
            ],
        )
        capture = self.match.court_capture_ids
        self.assertEqual(capture.scorer_source, "assistant_referee")
        self.assertEqual(capture.referee_confirmation, "pin")
        self.assertEqual(capture.referee_confirmed_by_id, self.referee)

    @freeze_time(GAME_DAY)
    def test_wrong_pin_never_blocks_and_locks_after_failures(self):
        self.referee._set_court_pin("4821")
        for _attempt in range(5):
            self.assertFalse(self.referee._check_court_pin("0000"))
        self.assertFalse(self.referee._check_court_pin("4821"))
        with self.assertRaises(ValidationError):
            self.referee._set_court_pin("1111")

    @freeze_time(GAME_DAY)
    def test_club_scorer_nominated_by_club_representative(self):
        role_type = self.env.ref("sports_federation_portal.role_type_competition_contact")
        for user in (self.official_user, self.other_user):
            self.env["federation.club.representative"].create(
                {
                    "club_id": self.club.id,
                    "partner_id": user.partner_id.id,
                    "user_id": user.id,
                    "role_type_id": role_type.id,
                }
            )
        nomination = self.service.with_user(self.official_user)._nominate_scorer(
            self.match.id, self.other_user.id
        )
        source, club = self.match._court_scoring_source(self.other_user)
        self.assertEqual((source, club), ("club_scorer", self.club))
        self.service.with_user(self.official_user)._withdraw_scorer(nomination.id)
        self.assertFalse(self.match._court_scoring_source(self.other_user)[0])
        with self.assertRaises(AccessError):
            self.service.with_user(self.approver)._nominate_scorer(
                self.match.id, self.other_user.id
            )

    @freeze_time(GAME_DAY)
    def test_match_log_is_court_evidence(self):
        service, device, _token = self.prepare()
        service._sync(
            device,
            self.match.id,
            [
                {
                    "key": str(uuid4()),
                    "operation": "log",
                    "payload": {
                        "events": [{"type": "timeout", "side": "home", "half": 1}]
                    },
                }
            ],
        )
        capture = self.match.court_capture_ids
        self.assertEqual(capture.match_log[0]["type"], "timeout")
        self.assertIn("Time-out", capture.evidence_summary)

    @freeze_time(GAME_DAY)
    def test_one_step_approval_by_tournament_manager(self):
        service, device, _token = self.prepare()
        service._sync(device, self.match.id, [self.command()])
        service._sync(device, self.match.id, [self.command("submit", revision=1)])
        self.assertEqual(self.match.result_state, "submitted")
        self.match.with_user(self.approver).action_approve_result_one_step()
        self.assertEqual(self.match.result_state, "approved")
        self.assertEqual(self.match.result_verified_by_id, self.approver)
        self.assertEqual(self.match.result_approved_by_id, self.approver)

    @freeze_time(GAME_DAY)
    def test_scorer_cannot_approve_own_result(self):
        # A court operator who is also result approver scored this match.
        self.env["federation.court.access"].create(
            {
                "matchday_id": self.matchday.id,
                "court_id": self.slot.court_id.id,
                "user_id": self.approver.id,
            }
        )
        commands = self.Commands.with_user(self.approver)
        args = [self.matchday.id, self.slot.court_id.id, self.match.id]
        base = commands.open_match(*args)
        commands.sync(
            *args,
            [
                {
                    "key": str(uuid4()),
                    "revision": base["revision"],
                    "operation": "submit",
                    "payload": {"home": 2, "away": 1},
                    "signature": base["signature"],
                }
            ],
        )
        self.assertEqual(self.match.result_state, "submitted")
        with self.assertRaises(ValidationError):
            self.match.with_user(self.approver).action_approve_result_one_step()


@tagged("post_install", "-at_install", "sf_live_workspace")
class TestCourtAppShell(HttpCase):
    def test_app_shell_and_service_worker_are_public(self):
        page = self.url_open("/court/app")
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="court-app"', page.text)
        worker = self.url_open("/court/sw.js")
        self.assertEqual(worker.headers.get("Service-Worker-Allowed"), "/court/")
        self.assertNotIn("__VERSION__", worker.text)
        self.assertNotIn("__FILES__", worker.text)

    def test_api_requires_a_device_token(self):
        response = self.url_open(
            "/court/api/pack",
            data="{}",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 401)
