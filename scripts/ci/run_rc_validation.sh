#!/usr/bin/env bash
set -euo pipefail

lane="${1:-all}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

modules="sports_federation_base,sports_federation_people,sports_federation_rules,sports_federation_tournament,sports_federation_competition_core,sports_federation_registration,sports_federation_result_control,sports_federation_format,sports_federation_venues,sports_federation_calendar,sports_federation_scheduling,sports_federation_schedule_approval,sports_federation_matchday,sports_federation_officiating,sports_federation_rosters,sports_federation_standings,sports_federation_portal,sports_federation_public_site,sports_federation_notifications,sports_federation_compliance,sports_federation_discipline,sports_federation_governance,sports_federation_import_tools,sports_federation_finance_bridge,sports_federation_reporting,sports_federation_demo"
db_name="${DB_NAME:-sf_rc_validation}"
upgrade_db_name="${UPGRADE_DB_NAME:-sf_rc_upgrade}"
compose_file="${RC_COMPOSE_FILE:-$repo_root/ci/docker-compose.ci.yaml}"
compose_project="${RC_COMPOSE_PROJECT:-sf_rc_${USER:-user}_$$}"
compose_project="${compose_project,,}"
compose_project="${compose_project//[^a-z0-9_-]/_}"
config_path="${RC_ODOO_CONFIG_PATH:-${TMPDIR:-/tmp}/${compose_project}.conf}"
ci_postgres_user="${CI_POSTGRES_USER:-odoo}"
ci_postgres_password="${CI_POSTGRES_PASSWORD:-odoo}"
ci_postgres_db="${CI_POSTGRES_DB:-postgres}"
ci_odo_db_host="${CI_ODOO_DB_HOST:-ci-db}"
ci_odo_db_port="${CI_ODOO_DB_PORT:-5432}"
compose=(docker compose -p "$compose_project" -f "$compose_file")
common=(--no-http --stop-after-init --without-demo=all --log-level=test)

export CI_PROJECT_NAME="$compose_project"
export CI_POSTGRES_USER="$ci_postgres_user"
export CI_POSTGRES_PASSWORD="$ci_postgres_password"
export CI_POSTGRES_DB="$ci_postgres_db"
export CI_ODOO_DB_HOST="$ci_odo_db_host"
export CI_ODOO_DB_PORT="$ci_odo_db_port"
export CI_ODOO_CONFIG_PATH="$config_path"

validate_database_name() {
  local database="$1"
  if [[ ! "$database" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ ]]; then
    echo "ERROR: invalid PostgreSQL database name: $database" >&2
    exit 2
  fi
}

require_compose() {
  command -v docker >/dev/null 2>&1 || {
    echo "ERROR: Docker is required for Odoo RC validation." >&2
    exit 2
  }
  docker compose version >/dev/null 2>&1 || {
    echo "ERROR: Docker Compose is required for Odoo RC validation." >&2
    exit 2
  }
}

write_config() {
  if [[ ! -f "$config_path" ]]; then
    cat > "$config_path" <<EOF
[options]
db_host = $ci_odo_db_host
db_port = $ci_odo_db_port
db_user = $ci_postgres_user
db_password = $ci_postgres_password
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons
data_dir = /var/lib/odoo
list_db = False
http_interface = 127.0.0.1
without_demo = True
log_level = info
EOF
    chmod 0644 "$config_path"
  fi
}

ensure_stack() {
  require_compose
  write_config
  "${compose[@]}" up -d --wait ci-db
  "${compose[@]}" exec -T \
    -e PGPASSWORD="$ci_postgres_password" \
    ci-db psql -h 127.0.0.1 -U "$ci_postgres_user" -d "$ci_postgres_db" \
    -v ON_ERROR_STOP=1 -c "SELECT 1" >/dev/null
}

ensure_database() {
  local database="$1"
  validate_database_name "$database"
  ensure_stack
  if ! "${compose[@]}" exec -T ci-db \
    psql -U "$ci_postgres_user" -d "$ci_postgres_db" -Atc \
    "SELECT 1 FROM pg_database WHERE datname='$database'" | grep -q '^1$'; then
    "${compose[@]}" exec -T ci-db \
      psql -U "$ci_postgres_user" -d "$ci_postgres_db" \
      -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"$database\" OWNER \"$ci_postgres_user\";"
  fi
}

cleanup_compose() {
  require_compose
  "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f "$config_path"
}

if [[ "${RC_COMPOSE_RETAIN:-0}" != "1" ]]; then
  trap cleanup_compose EXIT
fi

print_odoo_failure() {
  local exit_code="$1" logfile="${ODOO_LOGFILE:-$repo_root/odoo-rc.log}"
  echo "ERROR: Odoo RC lane '$lane' failed with exit code $exit_code." >&2
  if [[ -f "$logfile" ]]; then
    echo "--- Odoo failure summary ---" >&2
    grep -E "(^|[[:space:]])(ERROR|CRITICAL)[[:space:]]|FAIL:|ERROR:|[0-9]+ failed|[0-9]+ error" "$logfile" | tail -n 120 >&2 || true
    echo "--- Last 200 Odoo log lines ---" >&2
    tail -n 200 "$logfile" >&2 || true
  fi
  return "$exit_code"
}

run_odoo() {
  local logfile="${ODOO_LOGFILE:-$repo_root/odoo-rc.log}"
  local odoo_args=("$@")
  : > "$logfile"
  ensure_stack
  local container_command
  container_command="$(cat <<'EOF'
set -eu
if [ ! -e /usr/lib/python3/dist-packages/odoo-bin ]; then
  ln -s /usr/bin/odoo /usr/lib/python3/dist-packages/odoo-bin
fi
if command -v gosu >/dev/null 2>&1; then
  exec gosu odoo odoo "$@"
elif command -v runuser >/dev/null 2>&1; then
  exec runuser -u odoo -- odoo "$@"
else
  exec odoo "$@"
fi
EOF
)"
  if "${compose[@]}" run --rm ci-odoo sh -lc "$container_command" -- \
    "${odoo_args[@]}" >"$logfile" 2>&1; then
    grep -E "odoo.tests.result:|[0-9]+ post-tests in" "$logfile" | tail -n 5 || true
    return 0
  else
    local rc=$?
    print_odoo_failure "$rc"
    return "$rc"
  fi
}

static_checks() {
  python3 - <<'PY'
from pathlib import Path
import tokenize

for addon in sorted(Path('.').glob('sports_federation_*')):
    for path in sorted(addon.rglob('*.py')):
        with tokenize.open(path) as source_file:
            compile(source_file.read(), str(path), 'exec', dont_inherit=True)
print('Python syntax check passed without writing bytecode')
PY
  python3 - <<'PY'
from pathlib import Path
from xml.etree import ElementTree
for path in Path('.').glob('sports_federation_*'):
    for xml in path.rglob('*.xml'):
        ElementTree.parse(xml)
print('XML parse check passed')
PY
  git -c core.whitespace=cr-at-eol diff --check
  python3 ci/check_legacy_engine_removed.py
  python3 ci/check_portal_sudo_guard.py
  python3 ci/check_privileged_mutation_boundaries.py
  python3 ci/check_destructive_token_contract.py
  python3 ci/check_audit_acl_integrity.py
  python3 ci/check_privileged_command_contracts.py
  python3 ci/check_workflow_transition_foundation.py
  python3 ci/check_portal_competition_ownership.py
  python3 ci/check_officiating_contract.py
  python3 ci/check_registration_contract.py
  python3 ci/check_access_csv_integrity.py
  python3 ci/check_source_collector_contract.py
  python3 ci/check_addon_integrity.py
  python3 ci/check_test_discovery.py
  python3 ci/check_workflow_state_contracts.py
  python3 ci/check_fixture_ownership_contract.py
  python3 ci/check_rules_contract.py
  python3 ci/check_competition_pipeline_contract.py
  python3 ci/check_schedule_handoff_contract.py
  python3 ci/check_schedule_amendment_contract.py
  python3 ci/check_publication_integrity_contract.py
  python3 ci/check_public_competition_contract.py
  python3 ci/check_doc_freshness.py
  python3 ci/check_delivery_language.py
  python3 ci/check_competition_ui_workflow.py
  python3 ci/check_release_qualification.py
  python3 ci/check_release_focus_contract.py
  python3 ci/check_rc_product_readiness.py
  python3 ci/check_rc_usability.py
  python3 ci/check_retention_visibility_contract.py
  python3 ci/check_migration_rehearsal_contract.py
  if command -v node >/dev/null 2>&1; then
    while IFS= read -r -d '' file; do node --check "$file"; done < <(
      find sports_federation_* -path '*/static/src/*.js' -type f -print0
    )
  fi
}

run_tags() {
  local tags="$1"
  run_odoo "${common[@]}" -d "$db_name" -u "$modules" \
    --test-enable --test-tags "$tags"
}

assert_modules_installed() {
  local database="$1"
  validate_database_name "$database"
  ensure_stack
  local installed
  installed="$(
    "${compose[@]}" exec -T ci-db psql \
      -U "$ci_postgres_user" -d "$database" --tuples-only --no-align \
      --command="SELECT count(*) FROM ir_module_module WHERE name = ANY(string_to_array('$modules', ',')) AND state = 'installed'" \
      | tr -d '[:space:]'
  )"
  local expected
  expected="$(awk -F',' '{print NF}' <<<"$modules")"
  if [[ "$installed" != "$expected" ]]; then
    echo "ERROR: upgrade database $database has $installed of $expected required modules installed" >&2
    exit 2
  fi
}

run_upgrade() {
  assert_modules_installed "$upgrade_db_name"
  run_odoo "${common[@]}" -d "$upgrade_db_name" -u "$modules"
}

case "$lane" in
  cleanup) cleanup_compose ;;
  preflight) python3 ci/check_release_workspace.py ;;
  static) static_checks ;;
  install)
    ensure_database "$db_name"
    run_odoo "${common[@]}" -d "$db_name" -i "$modules" \
      --test-enable --test-tags 'standard'
    ;;
  upgrade) run_upgrade ;;
  core) run_tags 'sf_competition_core,sf_stage_graph,sf_calendar_slot_timeline,sf_fairness_solver,/sports_federation_officiating,/sports_federation_result_control,/sports_federation_notifications' ;;
  portal) run_tags '/sports_federation_portal,sf_frontend_http,sf_frontend_accessibility,sf_frontend_mobile' ;;
  public) run_tags '/sports_federation_public_site' ;;
  performance)
    python3 ci/check_performance_qualification.py
    run_tags '/sports_federation_standings:TestStandingsPerformance,/sports_federation_reporting:TestReportSnapshot,/sports_federation_reporting:TestYearFourReporting,/sports_federation_public_site:TestPublicSiteNewEndpoints'
    ;;
  acceptance) run_tags 'sf_operator_acceptance,sf_browser_competition_lifecycle,sf_browser_finance_bridge,sf_browser_public_site,sf_release_focus' ;;
  focus) run_tags 'sf_browser_competition_lifecycle,sf_browser_finance_bridge,sf_browser_public_site,sf_release_focus' ;;
  full) run_tags 'standard' ;;
  all)
    python3 ci/check_release_workspace.py
    static_checks
    ensure_database "$db_name"
    run_odoo "${common[@]}" -d "$db_name" -i "$modules" \
      --test-enable --test-tags 'standard'
    run_tags 'sf_competition_core,sf_stage_graph,sf_calendar_slot_timeline,sf_fairness_solver,/sports_federation_officiating,/sports_federation_result_control,/sports_federation_notifications'
    ensure_database "$upgrade_db_name"
    run_odoo "${common[@]}" -d "$upgrade_db_name" -i "$modules" \
      --test-enable --test-tags 'standard'
    run_upgrade
    run_tags '/sports_federation_portal,sf_frontend_http,sf_frontend_accessibility,sf_frontend_mobile'
    run_tags '/sports_federation_public_site'
    python3 ci/check_performance_qualification.py
    run_tags '/sports_federation_standings:TestStandingsPerformance,/sports_federation_reporting:TestReportSnapshot,/sports_federation_reporting:TestYearFourReporting,/sports_federation_public_site:TestPublicSiteNewEndpoints'
    run_tags 'sf_operator_acceptance,sf_browser_competition_lifecycle,sf_browser_finance_bridge,sf_browser_public_site,sf_release_focus'
    run_tags 'standard'
    ;;
  *) echo "Usage: $0 {preflight|static|install|upgrade|core|portal|public|performance|acceptance|focus|full|cleanup|all}" >&2; exit 2 ;;
esac
