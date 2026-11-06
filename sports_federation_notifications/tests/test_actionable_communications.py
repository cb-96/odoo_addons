import base64
from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, HttpCase, tagged


class CommunicationFixture:
    @classmethod
    def _communication_fixture(cls):
        env = cls.env
        cls.user = (
            env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Communication recipient",
                    "login": "communications.recipient@example.test",
                    "password": "communications-test",
                    "email": "communications.recipient@example.test",
                    "group_ids": [
                        (
                            6,
                            0,
                            [
                                env.ref(
                                    "sports_federation_portal.group_federation_portal_club"
                                ).id
                            ],
                        )
                    ],
                }
            )
        )
        cls.other = (
            env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Other communication recipient",
                    "login": "communications.other@example.test",
                    "password": "communications-test",
                    "email": "communications.other@example.test",
                    "group_ids": [
                        (
                            6,
                            0,
                            [
                                env.ref(
                                    "sports_federation_portal.group_federation_portal_club"
                                ).id
                            ],
                        )
                    ],
                }
            )
        )
        cls.club = env["federation.club"].create(
            {"name": "Communication club", "code": "COMCL"}
        )
        cls.role = env["federation.club.role.type"].create(
            {"name": "Communication club role", "code": "communication_test"}
        )
        cls.rep = env["federation.club.representative"].create(
            {
                "club_id": cls.club.id,
                "partner_id": cls.user.partner_id.id,
                "user_id": cls.user.id,
                "role_type_id": cls.role.id,
            }
        )
        cls.player = env["federation.player"].create(
            {"first_name": "Test", "last_name": "Participant", "club_id": cls.club.id}
        )
        cls.document = env["federation.player.parental.approval"].create(
            {
                "player_id": cls.player.id,
                "guardian_name": "Test contact",
                "approval_date": fields.Date.today(),
                "submitted_by_id": cls.user.id,
                "approval_document": base64.b64encode(b"%PDF-1.4 test evidence"),
                "approval_document_filename": "test.pdf",
                "review_note": "Replace the unreadable signature page.",
            }
        )
        cls.service = env["federation.notification.service"]

    def _publish(self, key="test-event", routes=None):
        return self.service._publish_action(
            self.document,
            "document_returned",
            key,
            routes if routes is not None else [(self.user.id, "club")],
        )


@tagged("post_install", "-at_install", "actionable_communications")
class TestActionableCommunications(CommunicationFixture, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._communication_fixture()

    def test_overlapping_roles_one_receipt(self):
        receipt = self._publish(
            routes=[
                (self.user.id, "club"),
                (self.user.id, "submitter"),
                (self.user.id, "club"),
            ]
        )
        self.assertEqual(len(receipt), 1)
        self.assertEqual(receipt.roles, "club, submitter")
        self.assertEqual(len(receipt.delivery_ids), 1)

    def test_event_replay_one_receipt_and_delivery(self):
        first = self._publish()
        self.assertEqual(first, self._publish())
        self.assertEqual(len(first.delivery_ids), 1)

    def test_unauthorised_recipient_is_not_created(self):
        self.assertFalse(self._publish(routes=[(self.other.id, "club")]))

    def test_inactive_recipient_is_not_created(self):
        self.user.active = False
        self.assertFalse(self._publish())

    def test_acknowledgement_does_not_complete_document(self):
        receipt = self._publish()
        before = self.document.state
        receipt._acknowledge_for(self.user)
        self.assertTrue(receipt.acknowledged_on)
        self.assertEqual(receipt.acknowledged_by_id, self.user)
        self.assertEqual(self.document.state, before)

    def test_acknowledgement_is_idempotent(self):
        receipt = self._publish()
        receipt._acknowledge_for(self.user)
        timestamp = receipt.acknowledged_on
        receipt._acknowledge_for(self.user)
        self.assertEqual(receipt.acknowledged_on, timestamp)

    def test_other_user_cannot_acknowledge(self):
        with self.assertRaises(AccessError):
            self._publish()._acknowledge_for(self.other)

    def test_other_user_cannot_read_receipt(self):
        receipt = self._publish()
        with self.assertRaises(AccessError):
            receipt.with_user(self.other).read(["name"])

    def test_recipient_cannot_reassign_receipt(self):
        with self.assertRaises(AccessError):
            self._publish().with_user(self.user).write({"recipient_id": self.other.id})

    def test_preferences_are_own_user_only(self):
        model = self.env["federation.communication.preference"].with_user(self.user)
        with self.assertRaises(AccessError):
            model._save_for_user(self.other, {"document_returned": "inbox"})

    def test_invalid_preferences_change_nothing(self):
        model = self.env["federation.communication.preference"].with_user(self.user)
        with self.assertRaises(ValidationError):
            model._save_for_user(
                self.user, {"document_returned": "inbox", "schedule_change": "invalid"}
            )
        self.assertEqual(model._mode_for(self.user, "document_returned"), "immediate")

    def test_inbox_only_keeps_receipt_without_mail(self):
        self.env["federation.communication.preference"].with_user(
            self.user
        )._save_for_user(self.user, {"document_returned": "inbox"})
        receipt = self._publish()
        self.assertEqual(receipt.delivery_ids.state, "suppressed")
        self.assertFalse(receipt.delivery_ids.mail_id)

    def test_digest_defers_email(self):
        self.env["federation.communication.preference"].with_user(
            self.user
        )._save_for_user(self.user, {"document_returned": "digest"})
        receipt = self._publish()
        self.assertFalse(receipt.delivery_ids)

    def test_revoked_scope_cannot_open_receipt(self):
        receipt = self._publish()
        self.rep.active = False
        with self.assertRaises(AccessError):
            receipt._presentation(self.user)

    def test_revoked_scope_cancels_pending_delivery(self):
        delivery = self._publish().delivery_ids
        self.rep.active = False
        delivery._queue_email()
        self.assertEqual(delivery.state, "cancelled")
        self.assertFalse(delivery.mail_id)

    def test_preference_change_cancels_pending_email(self):
        delivery = self._publish().delivery_ids
        self.env["federation.communication.preference"].with_user(
            self.user
        )._save_for_user(self.user, {"document_returned": "inbox"})
        delivery._queue_email()
        self.assertEqual(delivery.state, "cancelled")

    def test_queue_replay_reuses_mail(self):
        delivery = self._publish().delivery_ids
        delivery._queue_email()
        mail = delivery.mail_id
        delivery._queue_email()
        self.assertEqual(delivery.mail_id, mail)
        self.assertEqual(delivery.attempts, 1)

    def test_failed_retry_reuses_mail_and_business_record(self):
        delivery = self._publish().delivery_ids
        delivery._queue_email()
        mail = delivery.mail_id
        before = self.document.write_date
        mail.write({"state": "exception"})
        delivery._fail("Controlled test failure")
        delivery._queue_email(retry=True)
        self.assertEqual(delivery.mail_id, mail)
        self.assertEqual(delivery.attempts, 2)
        self.assertEqual(self.document.write_date, before)
        self.assertEqual(len(delivery.receipt_ids), 1)

    def test_sent_delivery_is_not_requeued(self):
        delivery = self._publish().delivery_ids
        delivery._queue_email()
        delivery.mail_id.write({"state": "sent"})
        delivery._accepted()
        attempts = delivery.attempts
        delivery._queue_email(retry=True)
        self.assertEqual(delivery.attempts, attempts)
        self.assertEqual(delivery.state, "sent")

    def test_missing_email_has_actionable_failure(self):
        self.user.partner_id.email = False
        delivery = self._publish().delivery_ids
        delivery._queue_email()
        self.assertEqual(delivery.state, "failed")
        self.assertIn("email", delivery.failure_note)
        self.user.partner_id.email = "recovered@example.test"
        delivery._queue_email(retry=True)
        self.assertEqual(delivery.state, "queued")

    def test_recipient_cannot_retry_delivery(self):
        delivery = self._publish().delivery_ids
        delivery._fail("Test failure")
        with self.assertRaises(AccessError):
            delivery.with_user(self.user).action_retry_delivery()

    def test_missing_previously_queued_mail_is_quarantined(self):
        delivery = self._publish().delivery_ids
        delivery._queue_email()
        delivery.mail_id.unlink()
        delivery._fail("Missing queued mail")
        with self.assertRaises(ValidationError):
            delivery._queue_email(retry=True)

    def test_document_return_trigger_contains_correction(self):
        self.document.action_request_replacement()
        receipt = (
            self.env["federation.communication.receipt"]
            .sudo()
            .search(
                [
                    ("target_model", "=", self.document._name),
                    ("target_res_id", "=", self.document.id),
                    ("recipient_id", "=", self.user.id),
                ]
            )
        )
        self.assertEqual(len(receipt), 1)
        info = receipt._presentation(self.user)
        self.assertIn("signature page", info["detail"])
        self.assertEqual(
            info["url"], "/my/players/%s/parental-approvals" % self.player.id
        )

    def test_repeated_return_write_has_no_duplicate(self):
        self.document.action_request_replacement()
        self.document.with_context(allow_verified_parental_approval_write=True).write(
            {"state": "replacement_requested"}
        )
        self.assertEqual(
            self.env["federation.communication.receipt"]
            .sudo()
            .search_count(
                [
                    ("target_model", "=", self.document._name),
                    ("target_res_id", "=", self.document.id),
                    ("recipient_id", "=", self.user.id),
                ]
            ),
            1,
        )

    def test_mail_send_rechecks_revoked_scope_without_provider_call(self):
        delivery = self._publish().delivery_ids
        delivery._queue_email()
        self.rep.active = False
        delivery.mail_id.send()
        self.assertEqual(delivery.mail_id.state, "cancel")
        self.assertEqual(delivery.state, "cancelled")

    def test_mail_does_not_copy_private_review_note(self):
        delivery = self._publish().delivery_ids
        delivery._queue_email()
        self.assertNotIn("signature page", delivery.mail_id.body_html)
        self.assertIn("/my/notifications/", delivery.mail_id.body_html)

    def test_linked_replacement_waits_for_review(self):
        self.document.action_request_replacement()
        self.document.copy({"state": "draft", "replaces_approval_id": self.document.id})
        info = self._publish()._presentation(self.user)
        self.assertFalse(info["complete"])
        self.assertEqual(info["task_state"], "Waiting for federation review")

    def test_verified_replacement_completes_correction_not_acknowledgement(self):
        self.document.action_request_replacement()
        replacement = self.document.copy(
            {"state": "draft", "replaces_approval_id": self.document.id}
        )
        replacement.action_verify()
        receipt = self._publish()
        self.assertTrue(receipt._presentation(self.user)["complete"])
        self.assertFalse(receipt.acknowledged_on)
        self.assertEqual(self.document.state, "replacement_requested")

    def test_escalation_is_idempotent(self):
        delivery = self._publish().delivery_ids
        delivery._fail("Controlled failure")
        delivery._escalate()
        count = len(delivery.activity_ids)
        delivery._escalate()
        self.assertEqual(len(delivery.activity_ids), count)

    def test_preferences_other_user_cannot_read(self):
        model = self.env["federation.communication.preference"].with_user(self.user)
        model._save_for_user(self.user, {"document_returned": "inbox"})
        preference = model.sudo().search([("user_id", "=", self.user.id)], limit=1)
        with self.assertRaises(AccessError):
            preference.with_user(self.other).read(["mode"])


@tagged("post_install", "-at_install", "actionable_communications")
class TestCommunicationHttp(CommunicationFixture, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._communication_fixture()
        cls.receipt = cls.service._publish_action(
            cls.document, "document_returned", "http-event", [(cls.user.id, "club")]
        )

    def test_inbox_renders_action_and_preferences(self):
        self.authenticate(self.user.login, "communications-test")
        response = self.url_open("/my/notifications")
        self.assertEqual(response.status_code, 200)
        self.assertIn("signature page", response.text)
        self.assertIn("Open relevant task", response.text)
        self.assertIn("/my/notifications/preferences", response.text)

    def test_detail_distinguishes_three_states(self):
        self.authenticate(self.user.login, "communications-test")
        response = self.url_open("/my/notifications/%s" % self.receipt.id)
        self.assertEqual(response.status_code, 200)
        for label in ("Email delivery", "Acknowledgement", "Underlying task"):
            self.assertIn(label, response.text)

    def test_other_user_gets_404(self):
        self.authenticate(self.other.login, "communications-test")
        self.assertEqual(
            self.url_open("/my/notifications/%s" % self.receipt.id).status_code, 404
        )

    def test_preferences_render(self):
        self.authenticate(self.user.login, "communications-test")
        response = self.url_open("/my/notifications/preferences")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Save preferences", response.text)

    def test_acknowledgement_requires_csrf(self):
        self.authenticate(self.user.login, "communications-test")
        response = self.url_open(
            "/my/notifications/%s/acknowledge" % self.receipt.id,
            data={},
            method="POST",
        )
        self.assertEqual(response.status_code, 400)

    def test_direct_link_reaches_document_page(self):
        self.authenticate(self.user.login, "communications-test")
        response = self.url_open("/my/notifications/%s/open" % self.receipt.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn("/parental-approvals", response.url)
