from pathlib import Path

from lxml import etree

from odoo.tests.common import TransactionCase


class TestPortalTemplateAccessibility(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        views_dir = Path(__file__).resolve().parents[1] / "views"
        cls.template_roots = {
            "portal_templates": etree.parse(
                str(views_dir / "portal_templates.xml")
            ).getroot(),
            "portal_roster_templates": etree.parse(
                str(views_dir / "portal_roster_templates.xml")
            ).getroot(),
            "portal_tournament_workspace_templates": etree.parse(
                str(views_dir / "portal_tournament_workspace_templates.xml")
            ).getroot(),
            "portal_officiating_templates": etree.parse(
                str(views_dir / "portal_officiating_templates.xml")
            ).getroot(),
        }

    def _template(self, file_key, template_id):
        templates = self.template_roots[file_key].xpath(
            f".//template[@id='{template_id}']"
        )
        self.assertTrue(
            templates, f"Template {template_id} should exist in {file_key}."
        )
        return templates[0]

    def _assert_controls_have_labels(self, file_key, template_id):
        template = self._template(file_key, template_id)
        controls = template.xpath(
            ".//form//*[self::input or self::select or self::textarea][not(@type='hidden')]"
        )
        self.assertTrue(
            controls, f"Template {template_id} should expose form controls."
        )
        for control in controls:
            control_id = control.get("id")
            self.assertTrue(
                control_id
                or control.get("aria-label")
                or control.get("aria-labelledby"),
                f"Control {control.get('name')} in {template_id} should expose an accessible name.",
            )
            if control.get("aria-label") or control.get("aria-labelledby"):
                continue
            labels = template.xpath(f".//label[@for='{control_id}']")
            self.assertTrue(
                labels,
                f"Control {control.get('name')} in {template_id} should have a matching label.",
            )

    def _assert_alert_roles(self, file_key, template_id):
        template = self._template(file_key, template_id)
        alerts = template.xpath(
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' alert ')]"
        )
        self.assertTrue(
            alerts, f"Template {template_id} should expose feedback alerts."
        )
        for alert in alerts:
            self.assertIn(
                alert.get("role"),
                {"alert", "status"},
                f"Alert in {template_id} should declare an assistive role.",
            )

    def _assert_tables_have_captions_and_scoped_headers(self, file_key, template_id):
        template = self._template(file_key, template_id)
        tables = template.xpath(".//table[.//thead]")
        self.assertTrue(tables, f"Template {template_id} should contain data tables.")
        for table in tables:
            self.assertTrue(
                table.xpath("./caption")
                or table.get("aria-label")
                or table.get("aria-labelledby"),
                f"Table in {template_id} should expose a caption or accessible label.",
            )
            header_cells = table.xpath(".//thead//th")
            self.assertTrue(
                header_cells, f"Table in {template_id} should define column headers."
            )
            for header in header_cells:
                self.assertEqual(
                    header.get("scope"),
                    "col",
                    f"Header '{''.join(header.itertext()).strip()}' in {template_id} should scope the column.",
                )

    def test_core_portal_forms_have_explicit_labels(self):
        self._assert_controls_have_labels("portal_templates", "portal_my_team_new")
        self._assert_controls_have_labels(
            "portal_templates", "portal_season_registration_form"
        )

    def test_operational_portal_forms_have_explicit_labels(self):
        self._assert_controls_have_labels(
            "portal_roster_templates", "portal_my_roster_edit"
        )
        self._assert_controls_have_labels(
            "portal_roster_templates", "portal_my_roster_line_form"
        )
        self._assert_controls_have_labels(
            "portal_roster_templates", "portal_my_match_sheet_detail"
        )
        self._assert_controls_have_labels(
            "portal_officiating_templates", "portal_my_referee_assignment_detail"
        )

    def test_core_portal_feedback_uses_alert_roles(self):
        self._assert_alert_roles("portal_templates", "portal_my_team_new")
        self._assert_alert_roles("portal_templates", "portal_my_teams")
        self._assert_alert_roles("portal_templates", "portal_my_season_registrations")
        self._assert_alert_roles(
            "portal_templates", "portal_my_tournament_registrations"
        )
        self._assert_alert_roles("portal_templates", "portal_season_registration_form")

    def test_operational_portal_feedback_uses_alert_roles(self):
        self._assert_alert_roles("portal_roster_templates", "portal_my_rosters")
        self._assert_alert_roles("portal_roster_templates", "portal_my_roster_detail")
        self._assert_alert_roles(
            "portal_roster_templates", "portal_my_match_sheet_detail"
        )
        self._assert_alert_roles(
            "portal_tournament_workspace_templates", "portal_my_tournament_workspaces"
        )
        self._assert_alert_roles(
            "portal_officiating_templates", "portal_my_referee_assignments"
        )
        self._assert_alert_roles(
            "portal_officiating_templates", "portal_my_referee_assignment_detail"
        )

    def test_core_portal_tables_have_captions_and_header_scope(self):
        self._assert_tables_have_captions_and_scoped_headers(
            "portal_templates", "portal_my_teams"
        )
        self._assert_tables_have_captions_and_scoped_headers(
            "portal_templates", "portal_my_season_registrations"
        )
        self._assert_tables_have_captions_and_scoped_headers(
            "portal_templates", "portal_my_tournament_registrations"
        )

    def test_operational_portal_tables_have_captions_and_header_scope(self):
        self._assert_tables_have_captions_and_scoped_headers(
            "portal_roster_templates", "portal_my_rosters"
        )
        self._assert_tables_have_captions_and_scoped_headers(
            "portal_roster_templates", "portal_my_roster_detail"
        )
        self._assert_tables_have_captions_and_scoped_headers(
            "portal_roster_templates", "portal_my_match_sheets"
        )
        self._assert_tables_have_captions_and_scoped_headers(
            "portal_roster_templates", "portal_my_match_sheet_detail"
        )
        self._assert_tables_have_captions_and_scoped_headers(
            "portal_roster_templates", "portal_my_match_day"
        )
        self._assert_tables_have_captions_and_scoped_headers(
            "portal_officiating_templates", "portal_my_referee_assignments"
        )
        self._assert_tables_have_captions_and_scoped_headers(
            "portal_tournament_workspace_templates",
            "portal_my_tournament_workspace_detail",
        )
