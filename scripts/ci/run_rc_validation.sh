#!/usr/bin/env bash
set -euo pipefail

lane="${1:-all}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

modules="sports_federation_base,sports_federation_rules,sports_federation_tournament,sports_federation_competition_engine,sports_federation_officiating,sports_federation_result_control,sports_federation_notifications,sports_federation_portal"
odoo_bin="${ODOO_BIN:-$repo_root/_odoo/odoo-bin}"
addons_path="${ADDONS_PATH:-$repo_root,$repo_root/_odoo/addons}"
db_name="${DB_NAME:-sf_rc_validation}"
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
  git diff --check
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

case "$lane" in
  static) static_checks ;;
  install)
    require_odoo
    "${common[@]}" -i "$modules" --test-enable --test-tags '/sports_federation_base,/sports_federation_rules,/sports_federation_tournament'
    ;;
  core) run_tags 'sf_competition_workspace,/sports_federation_officiating,/sports_federation_result_control,/sports_federation_notifications' ;;
  portal) run_tags '/sports_federation_portal,sf_frontend_http,sf_frontend_accessibility,sf_frontend_mobile' ;;
  concurrency) run_tags 'sf_ws_true_concurrency' ;;
  simulation) run_tags 'sf_production_simulation' ;;
  all)
    static_checks
    require_odoo
    "${common[@]}" -i "$modules" --test-enable --test-tags '/sports_federation_base,/sports_federation_rules,/sports_federation_tournament'
    run_tags 'sf_competition_workspace,/sports_federation_officiating,/sports_federation_result_control,/sports_federation_notifications'
    run_tags '/sports_federation_portal,sf_frontend_http,sf_frontend_accessibility,sf_frontend_mobile'
    run_tags 'sf_ws_true_concurrency'
    run_tags 'sf_production_simulation'
    ;;
  *) echo "Usage: $0 {static|install|core|portal|concurrency|simulation|all}" >&2; exit 2 ;;
esac
