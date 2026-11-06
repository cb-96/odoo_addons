"""Archive settings on the retired planner before old columns are removed."""

import logging

_logger = logging.getLogger(__name__)

PLANNER_FIELDS = (
    "max_consecutive_matches_per_team",
    "minimum_rest_minutes",
    "planning_format",
    "pool_count",
    "pool_qualifier_count",
    "workspace_state",
)


def migrate(cr, version):
    cr.execute("SELECT to_regclass('public.federation_tournament')")
    if not cr.fetchone()[0]:
        return

    cr.execute("""
        SELECT column_name
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'federation_tournament'
        """)
    available_fields = {row[0] for row in cr.fetchall() if row[0] in PLANNER_FIELDS}
    if not available_fields:
        return

    cr.execute(
        "ALTER TABLE federation_tournament "
        "ADD COLUMN IF NOT EXISTS retired_planner_settings jsonb"
    )
    json_pairs = ", ".join(
        f"'{field_name}', {field_name}"
        for field_name in PLANNER_FIELDS
        if field_name in available_fields
    )
    populated_filter = " OR ".join(
        f"{field_name} IS NOT NULL"
        for field_name in PLANNER_FIELDS
        if field_name in available_fields
    )
    cr.execute(f"""
        UPDATE federation_tournament
           SET retired_planner_settings =
               COALESCE(retired_planner_settings, '{{}}'::jsonb)
               || jsonb_build_object({json_pairs})
         WHERE {populated_filter}
        """)
    if cr.rowcount:
        _logger.info("Archived planner settings for %s tournament(s).", cr.rowcount)
