#!/usr/bin/env bash
set -euo pipefail

lane="${1:-all}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

modules="sports_federation_base,sports_federation_people,sports_federation_rules,sports_federation_tournament,sports_federation_competition_core,sports_federation_registration,sports_federation_result_control,sports_federation_format,sports_federation_venues,sports_federation_calendar,sports_federation_scheduling,sports_federation_schedule_approval,sports_federation_matchday,sports_federation_officiating,sports_federation_rosters,sports_federation_standings,sports_federation_portal,sports_federation_public_site,sports_federation_notifications,sports_federation_compliance,sports_federation_discipline,sports_federation_governance,sports_federation_import_tools,sports_federation_finance_bridge,sports_federation_reporting,sports_federation_demo"
odoo_bin="${ODOO_BIN:-$repo_root/_odoo/odoo-bin}"
addons_path="${ADDONS_PATH:-$repo_root,$repo_root/_odoo/addons}"
db_name="${DB_NAME:-sf_rc_validation}"
upgrade_db_name="${UPGRADE_DB_NAME:-sf_rc_upgrade}"
common=(
  "$odoo_bin" -d "$db_name"
  --db_host="${PGHOST:-127.0.0.1}"
  --db_port="${PGPORT:-5432}"
  --db_user="${PGUSER:-odoo}"
  --db_password="${PGPASSWORD:-odoo}"
  --addons-path="$addons_path"
  --without-demo=all
  --stop-after-init
  --log-level=test
  --logfile="${ODOO_LOGFILE:-$repo_root/odoo-rc.log}"
)

require_odoo() {
  if [[ ! -x "$odoo_bin" ]]; then
    echo "ERROR: ODOO_BIN is not executable: $odoo_bin" >&2
    exit 2
  fi
}

static_checks() {
  python3 -m compileall -q sports_federation_*
  python3 - <<'PY'
from pathlib import Path
from xml.etree import ElementTree
for path in Path('.').glob('sports_federation_*'):
    for xml in path.rglob('*.xml'):
        ElementTree.parse(xml)
print('XML parse check passed')
PY
  git -c core.whitespace=cr-at-eol diff --check
  python3 ci/check_test_discovery.py
  if command -v node >/dev/null 2>&1; then
    while IFS= read -r -d '' file; do node --check "$file"; done < <(
      find sports_federation_* -path '*/static/src/*.js' -type f -print0
    )
  fi
}

run_tags() {
  local tags="$1"
  require_odoo
  "${common[@]}" -u "$modules" --test-enable --test-tags "$tags"
}

assert_modules_installed() {
  local database="$1"
  if ! command -v psql >/dev/null 2>&1; then
    echo "ERROR: psql is required for upgrade qualification" >&2
    exit 2
  fi
  local installed
  installed="$(
    PGPASSWORD="${PGPASSWORD:-odoo}" psql       --host="${PGHOST:-127.0.0.1}"       --port="${PGPORT:-5432}"       --username="${PGUSER:-odoo}"       --dbname="$database"       --tuples-only --no-align       --command="SELECT count(*) FROM ir_module_module WHERE name = ANY(string_to_array('$modules', ',')) AND state = 'installed'"
  )"
  local expected
  expected="$(awk -F',' '{print NF}' <<<"$modules")"
  if [[ "$installed" != "$expected" ]]; then
    echo "ERROR: upgrade database $database has $installed of $expected required modules installed" >&2
    exit 2
  fi
}

run_upgrade() {
  require_odoo
  assert_modules_installed "$upgrade_db_name"
  local upgrade_common=("${common[@]}")
  upgrade_common[2]="$upgrade_db_name"
  "${upgrade_common[@]}" -u "$modules"
}

case "$lane" in
  static) static_checks ;;
  install)
    require_odoo
    "${common[@]}" -i "$modules" --test-enable --test-tags 'standard'
    ;;
  upgrade) run_upgrade ;;
  core) run_tags 'sf_competition_core,sf_stage_graph,sf_calendar_slot_timeline,sf_fairness_solver,/sports_federation_officiating,/sports_federation_result_control,/sports_federation_notifications' ;;
  portal) run_tags '/sports_federation_portal,sf_frontend_http,sf_frontend_accessibility,sf_frontend_mobile' ;;
  public) run_tags '/sports_federation_public_site' ;;
  full) run_tags 'standard' ;;
  all)
    static_checks
    require_odoo
    "${common[@]}" -i "$modules" --test-enable --test-tags 'standard'
    run_tags 'sf_competition_core,sf_stage_graph,sf_calendar_slot_timeline,sf_fairness_solver,/sports_federation_officiating,/sports_federation_result_control,/sports_federation_notifications'
    run_upgrade
    run_tags '/sports_federation_portal,sf_frontend_http,sf_frontend_accessibility,sf_frontend_mobile'
    run_tags '/sports_federation_public_site'
    run_tags 'standard'
    ;;
  *) echo "Usage: $0 {static|install|upgrade|core|portal|public|full|all}" >&2; exit 2 ;;
esac
