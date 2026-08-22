#!/usr/bin/env bash
set -euo pipefail
: "${ODOO_BIN:?Set ODOO_BIN to the odoo-bin executable}"
: "${ODOO_DATABASE:?Set ODOO_DATABASE to a disposable PostgreSQL database}"
: "${ODOO_ADDONS_PATH:?Set ODOO_ADDONS_PATH to include Odoo and this repository}"
MODULES="sports_federation_base,sports_federation_rules,sports_federation_tournament,sports_federation_competition_core,sports_federation_registration,sports_federation_format,sports_federation_venues,sports_federation_calendar,sports_federation_scheduling,sports_federation_schedule_approval,sports_federation_matchday,sports_federation_officiating,sports_federation_result_control,sports_federation_portal,sports_federation_notifications"
exec "$ODOO_BIN" --database "$ODOO_DATABASE" --addons-path "$ODOO_ADDONS_PATH"   --init "$MODULES" --test-enable --stop-after-init --log-level=test
