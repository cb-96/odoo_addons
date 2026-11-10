from odoo.tests.common import TransactionCase

ADVANCED_MENU_XMLIDS = (
    "sports_federation_competition_core.menu_competition_engine_competition_root",
    "sports_federation_base.menu_federation_planning",
    "sports_federation_navigation.menu_courts_venues",
    "sports_federation_officiating.menu_federation_officiating",
    "sports_federation_discipline.menu_federation_discipline",
    "sports_federation_base.menu_federation_business",
    "sports_federation_reporting.menu_federation_report_operator_checklist",
    "sports_federation_reporting.menu_federation_reporting_performance",
    "sports_federation_base.menu_federation_administration",
)

# Screens that are opened contextually and must no longer have a menu.
RETIRED_MENU_XMLIDS = (
    "sports_federation_base.menu_federation_master_data",
    "sports_federation_tournament.menu_federation_competition_edition",
    "sports_federation_tournament.menu_federation_tournament",
    "sports_federation_tournament.menu_federation_tournament_stages",
    "sports_federation_competition_core.menu_competition_overview_competition",
    "sports_federation_competition_core.menu_competition_engine_competition_technical",
    "sports_federation_registration.menu_create_competition",
    "sports_federation_scheduling.menu_generate_competition_schedule",
    "sports_federation_rules.menu_federation_rule_components",
    "sports_federation_people.menu_federation_player_license",
    "sports_federation_portal.menu_federation_portal_root",
    "sports_federation_portal.menu_federation_club_representative_portal",
    "sports_federation_officiating.menu_federation_matchday_assign_official",
    "sports_federation_discipline.menu_federation_sanction",
    "sports_federation_venues.menu_federation_venue_blackouts",
    "sports_federation_governance.menu_federation_override_outcome",
    "sports_federation_reporting.menu_federation_reporting",
    "sports_federation_reporting.menu_federation_report_workflow_exception",
    "sports_federation_navigation.menu_reports",
    "sports_federation_navigation.menu_needs_attention",
    "sports_federation_navigation.action_needs_attention",
    "sports_federation_portal.menu_federation_operation_task",
)


class TestFederationNavigation(TransactionCase):
    def _federation_menus(self):
        root = self.env.ref("sports_federation_base.menu_federation_root")
        return (
            self.env["ir.ui.menu"]
            .with_context(active_test=False)
            .search([("id", "child_of", root.id), ("id", "!=", root.id)])
        )

    def test_advanced_menus_are_limited_to_advanced_operators(self):
        advanced_group = self.env.ref(
            "sports_federation_base.group_federation_advanced_operator"
        )
        for menu_xmlid in ADVANCED_MENU_XMLIDS:
            with self.subTest(menu_xmlid=menu_xmlid):
                self.assertEqual(self.env.ref(menu_xmlid).group_ids, advanced_group)

    def test_publication_menu_also_allows_schedule_approvers(self):
        menu = self.env.ref("sports_federation_base.menu_federation_publication")
        expected_groups = {
            self.env.ref("sports_federation_base.group_federation_manager").id,
            self.env.ref(
                "sports_federation_schedule_approval.group_schedule_approver"
            ).id,
        }
        self.assertSetEqual(set(menu.group_ids.ids), expected_groups)

    def test_system_section_requires_developer_mode(self):
        menu = self.env.ref("sports_federation_base.menu_federation_system_health")
        self.assertEqual(menu.group_ids, self.env.ref("base.group_no_one"))

    def test_retired_menus_are_removed(self):
        for menu_xmlid in RETIRED_MENU_XMLIDS:
            with self.subTest(menu_xmlid=menu_xmlid):
                self.assertFalse(self.env.ref(menu_xmlid, raise_if_not_found=False))

    def test_menu_tree_is_shallow_and_openable(self):
        root = self.env.ref("sports_federation_base.menu_federation_root")
        for menu in self._federation_menus():
            with self.subTest(menu=menu.complete_name):
                depth, parent = 0, menu
                while parent and parent != root:
                    depth += 1
                    parent = parent.parent_id
                self.assertLessEqual(depth, 3)
                if menu.child_id:
                    self.assertFalse(
                        menu.action, "a menu with children cannot open its action"
                    )

    def test_app_opens_on_competition_hub(self):
        root = self.env.ref("sports_federation_base.menu_federation_root")
        hub = self.env.ref("sports_federation_setup_flow.menu_competition_setup_home")

        def first_action(menu):
            for child in menu.child_id.sorted(lambda item: (item.sequence, item.id)):
                if child.action:
                    return child
                found = first_action(child)
                if found:
                    return found
            return self.env["ir.ui.menu"]

        self.assertEqual(first_action(root), hub)

    def test_review_queue_is_manager_only(self):
        action = self.env["federation.operation.task"].action_open_review_queue()
        self.assertEqual(action["res_model"], "federation.operation.task")
        self.assertIn("('audience', '=', 'manager')", str(action["domain"]))
        menu = self.env.ref("sports_federation_navigation.menu_review_queue")
        self.assertEqual(
            menu.group_ids,
            self.env.ref("sports_federation_base.group_federation_manager"),
        )
