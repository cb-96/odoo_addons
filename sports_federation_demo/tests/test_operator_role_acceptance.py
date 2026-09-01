from odoo import Command
from odoo.tests.common import TransactionCase, tagged


@tagged('-at_install', 'post_install', 'sf_operator_acceptance')
class TestOperatorRoleAcceptance(TransactionCase):
    """Prove the release pilot uses explicit, independently assignable roles."""

    ROLE_MODELS = (
        ('sports_federation_registration.group_registration_manager', 'federation.registration.window'),
        ('sports_federation_format.group_competition_designer', 'federation.competition.structure'),
        ('sports_federation_calendar.group_calendar_planner', 'federation.matchday'),
        ('sports_federation_scheduling.group_schedule_planner', 'federation.schedule'),
        ('sports_federation_schedule_approval.group_schedule_approver', 'federation.schedule.review'),
        ('sports_federation_matchday.group_matchday_manager', 'federation.matchday.session'),
    )

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.users = {}
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        for index, (group_xmlid, _model) in enumerate(cls.ROLE_MODELS, start=1):
            group = cls.env.ref(group_xmlid)
            cls.users[group_xmlid] = Users.create({
                'name': f'Lifecycle Operator {index}',
                'login': f'lifecycle.operator.{index}@example.invalid',
                'group_ids': [Command.set([cls.env.ref('base.group_user').id, group.id])],
            })

    def test_each_phase_owner_can_read_the_owned_workspace(self):
        for group_xmlid, model_name in self.ROLE_MODELS:
            model = self.env[model_name].with_user(self.users[group_xmlid])
            self.assertTrue(model.check_access_rights('read', raise_exception=False), (group_xmlid, model_name))

    def test_planner_and_approver_are_distinct_operators(self):
        planner = self.users['sports_federation_scheduling.group_schedule_planner']
        approver = self.users['sports_federation_schedule_approval.group_schedule_approver']
        self.assertNotEqual(planner, approver)
        review_model = self.env['federation.schedule.review'].with_user(planner)
        self.assertFalse(review_model.check_access_rights('write', raise_exception=False))
