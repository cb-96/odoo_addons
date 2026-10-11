from odoo.tests.common import TransactionCase


ADVANCED_MENU_XMLIDS = (
    "sports_federation_base.menu_federation_season",
    "sports_federation_tournament.menu_federation_competition_edition",
    "sports_federation_tournament.menu_federation_competition",
    "sports_federation_format.menu_format_templates",
    "sports_federation_rules.menu_federation_competition_rules",
    "sports_federation_base.menu_federation_planning",
    "sports_federation_competition_core.menu_competition_engine_competition_root",
    "sports_federation_competition_core.menu_competition_engine_competition_technical",
    "sports_federation_tournament.menu_federation_matches",
    "sports_federation_rosters.menu_federation_match_sheets",
    "sports_federation_officiating.menu_federation_officiating",
    "sports_federation_venues.menu_federation_venues",
    "sports_federation_discipline.menu_federation_discipline",
    "sports_federation_base.menu_federation_business",
    "sports_federation_base.menu_federation_insights",
    "sports_federation_base.menu_federation_administration",
)


class TestFederationNavigation(TransactionCase):
    def test_advanced_menus_are_limited_to_advanced_operators(self):
        advanced_group = self.env.ref(
            "sports_federation_base.group_federation_advanced_operator"
        )

        for menu_xmlid in ADVANCED_MENU_XMLIDS:
            with self.subTest(menu_xmlid=menu_xmlid):
                menu = self.env.ref(menu_xmlid)
                self.assertEqual(menu.group_ids, advanced_group)

    def test_publication_menu_also_allows_schedule_approvers(self):
        menu = self.env.ref("sports_federation_base.menu_federation_publication")
        expected_groups = {
            self.env.ref(
                "sports_federation_base.group_federation_advanced_operator"
            ).id,
            self.env.ref(
                "sports_federation_schedule_approval.group_schedule_approver"
            ).id,
        }

        self.assertSetEqual(set(menu.group_ids.ids), expected_groups)
