import re
from pathlib import Path

from lxml import etree

from odoo.tests.common import TransactionCase

MIN_COLUMNS_FOR_RESPONSIVE = 5


class TestPortalTemplateMobile(TransactionCase):
    """Verify mobile-specific layout conventions in the largest portal templates.

    These checks complement the accessibility tests by validating that wide
    tables are horizontally scrollable, that action-button groups wrap on
    narrow viewports, and that no inline width constraints cause horizontal
    overflow on phone-sized screens.
    """

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

    # ------------------------------------------------------------------
    # Assertion helpers
    # ------------------------------------------------------------------

    def _assert_wide_tables_wrapped_responsive(self, file_key, template_id):
        """Tables with MIN_COLUMNS_FOR_RESPONSIVE+ header columns must live
        inside a ``table-responsive`` ancestor so they scroll on narrow screens.
        """
        template = self._template(file_key, template_id)
        tables = template.xpath(".//table[.//thead]")
        for table in tables:
            col_count = len(table.xpath(".//thead//th"))
            if col_count < MIN_COLUMNS_FOR_RESPONSIVE:
                continue
            # Walk up to find a table-responsive wrapper
            parent = table.getparent()
            found = False
            while parent is not None:
                classes = parent.get("class", "")
                if "table-responsive" in classes.split():
                    found = True
                    break
                parent = parent.getparent()
            self.assertTrue(
                found,
                f"Table with {col_count} columns in {template_id} "
                f"should be wrapped in a table-responsive container.",
            )

    def _assert_action_groups_wrap(self, file_key, template_id):
        """Button groups using ``d-flex`` should include ``flex-wrap`` so
        action buttons stack on phone-width viewports instead of overflowing.
        """
        template = self._template(file_key, template_id)
        groups = template.xpath(
            ".//*[contains(concat(' ', normalize-space(@class), ' '), ' d-flex ')]"
        )
        for group in groups:
            classes = group.get("class", "").split()
            if "d-flex" not in classes:
                continue
            # Only check groups that contain buttons or links
            has_actions = group.xpath("./*[self::button or self::a or self::form]")
            if not has_actions:
                continue
            self.assertIn(
                "flex-wrap",
                classes,
                f"Action group in {template_id} uses d-flex but is missing "
                f"flex-wrap for mobile overflow.",
            )

    def _assert_no_table_fixed_width_overflow(self, file_key, template_id):
        """Data tables (with <thead>) should not carry inline ``width`` styles
        on the <table> element itself, as this can force horizontal overflow
        on narrow viewports.
        """
        template = self._template(file_key, template_id)
        tables = template.xpath(".//table[.//thead]")
        for table in tables:
            style = table.get("style", "")
            self.assertFalse(
                re.search(r"width\s*:", style),
                f"Data table in {template_id} has an inline width style "
                f"that may cause mobile overflow.",
            )

    # ------------------------------------------------------------------
    # Core portal templates
    # ------------------------------------------------------------------

    def test_core_portal_wide_tables_wrapped(self):
        self._assert_wide_tables_wrapped_responsive(
            "portal_templates", "portal_my_teams"
        )
        self._assert_wide_tables_wrapped_responsive(
            "portal_templates", "portal_my_season_registrations"
        )
        self._assert_wide_tables_wrapped_responsive(
            "portal_templates", "portal_my_tournament_registrations"
        )

    def test_core_portal_no_table_fixed_width(self):
        self._assert_no_table_fixed_width_overflow(
            "portal_templates", "portal_my_teams"
        )
        self._assert_no_table_fixed_width_overflow(
            "portal_templates", "portal_my_season_registrations"
        )
        self._assert_no_table_fixed_width_overflow(
            "portal_templates", "portal_my_tournament_registrations"
        )

    # ------------------------------------------------------------------
    # Roster and match-day templates
    # ------------------------------------------------------------------

    def test_roster_portal_wide_tables_wrapped(self):
        self._assert_wide_tables_wrapped_responsive(
            "portal_roster_templates", "portal_my_rosters"
        )
        self._assert_wide_tables_wrapped_responsive(
            "portal_roster_templates", "portal_my_roster_detail"
        )
        self._assert_wide_tables_wrapped_responsive(
            "portal_roster_templates", "portal_my_match_sheets"
        )
        self._assert_wide_tables_wrapped_responsive(
            "portal_roster_templates", "portal_my_match_sheet_detail"
        )
        self._assert_wide_tables_wrapped_responsive(
            "portal_roster_templates", "portal_my_match_day"
        )

    def test_roster_portal_action_groups_wrap(self):
        self._assert_action_groups_wrap(
            "portal_roster_templates", "portal_my_roster_detail"
        )
        self._assert_action_groups_wrap(
            "portal_roster_templates", "portal_my_match_sheet_detail"
        )

    def test_roster_portal_no_table_fixed_width(self):
        self._assert_no_table_fixed_width_overflow(
            "portal_roster_templates", "portal_my_rosters"
        )
        self._assert_no_table_fixed_width_overflow(
            "portal_roster_templates", "portal_my_match_sheets"
        )
        self._assert_no_table_fixed_width_overflow(
            "portal_roster_templates", "portal_my_match_day"
        )

    # ------------------------------------------------------------------
    # Tournament workspace templates
    # ------------------------------------------------------------------

    def test_workspace_portal_wide_tables_wrapped(self):
        self._assert_wide_tables_wrapped_responsive(
            "portal_tournament_workspace_templates",
            "portal_my_tournament_workspace_detail",
        )

    # ------------------------------------------------------------------
    # Officiating templates
    # ------------------------------------------------------------------

    def test_officiating_portal_wide_tables_wrapped(self):
        self._assert_wide_tables_wrapped_responsive(
            "portal_officiating_templates", "portal_my_referee_assignments"
        )

    def test_officiating_portal_action_groups_wrap(self):
        self._assert_action_groups_wrap(
            "portal_officiating_templates",
            "portal_my_referee_assignment_detail",
        )
