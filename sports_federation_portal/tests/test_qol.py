from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase


class TestPortalQoL(TransactionCase):
    def test_task_assignment_never_widens_club_scope(self):
        a, b = self.env["federation.club"].create(
            [{"name": "QoL A", "code": "QOLA"}, {"name": "QoL B", "code": "QOLB"}]
        )
        partner = self.env["res.partner"].create({"name": "Delegate"})
        user = (
            self.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "Delegate",
                    "login": "qol.delegate@test",
                    "partner_id": partner.id,
                }
            )
        )
        role = self.env["federation.club.role.type"].search([], limit=1)
        self.env["federation.club.representative"].create(
            {
                "club_id": b.id,
                "partner_id": partner.id,
                "user_id": user.id,
                "role_type_id": role.id,
            }
        )
        task = self.env["federation.operation.task"].create(
            {
                "name": "Scoped",
                "task_type": "registration",
                "audience": "club",
                "responsible_club_id": a.id,
                "source_model": "x",
                "source_record_id": 1,
                "source_key": "x:1:qol",
            }
        )
        with self.assertRaises(ValidationError):
            task.action_assign_user(user)

    def test_task_bucket_marks_near_deadline(self):
        task = self.env["federation.operation.task"].create(
            {
                "name": "Soon",
                "task_type": "registration",
                "audience": "club",
                "deadline": fields.Datetime.now(),
                "source_model": "x",
                "source_record_id": 2,
                "source_key": "x:2:qol",
            }
        )
        self.assertIn(task.work_bucket, ("now", "soon"))
