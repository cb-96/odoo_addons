#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Sports Federation CI – run Odoo module tests in an isolated container.
#
# Usage:
#   bash ci/run_tests.sh                          # test all modules
#   bash ci/run_tests.sh --module sports_federation_base
#   bash ci/run_tests.sh --suite portal_public_ops
#   bash ci/run_tests.sh --module sports_federation_rosters --test-tags sf_rosters_participant_readiness --require-post-tests 1
#   bash ci/run_tests.sh --frontend-module sports_federation_portal
#   bash ci/run_tests.sh --affected-from origin/main --include-dependents
#   bash ci/run_tests.sh --list-suites
#   bash ci/run_tests.sh --keep                  # keep containers for debugging
#
# Requirements: docker compose current
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.ci.yaml"
ENV_FILE="$SCRIPT_DIR/.env"
EXAMPLE_ENV_FILE="$SCRIPT_DIR/.env.example"
GENERATED_CONF="$SCRIPT_DIR/odoo-ci.generated.runtime.conf"

if [[ -e "$GENERATED_CONF" ]]; then
  GENERATED_CONF="$(mktemp "$SCRIPT_DIR/odoo-ci.generated.conf.XXXXXX")"
fi

usage() {
  cat <<'EOF'
Usage:
  bash ci/run_tests.sh
  bash ci/run_tests.sh --module sports_federation_base
  bash ci/run_tests.sh --suite competition_core
  bash ci/run_tests.sh --suite portal_public_ops --keep-on-failure
  bash ci/run_tests.sh --module sports_federation_rosters --test-tags sf_rosters_participant_readiness --require-post-tests 1
  bash ci/run_tests.sh --list-suites

Options:
  --module, -m        Add a module to the install/test list. Repeatable.
  --suite, -s         Add a named test suite. Repeatable.
  --test-tags         Override Odoo --test-tags expression used for discovery.
  --require-post-tests Fail if discovered post-tests are below the provided minimum.
  --frontend-module   Run frontend-only checks for a module. Repeatable.
  --affected-from     Select modules changed since a git ref.
  --include-dependents Expand affected modules through manifest reverse dependencies.
  --list-suites       Print the available named suites.
  --keep, -k          Leave the Docker Compose stack running after the run.
  --keep-on-failure   Clean successful runs; retain failed runtime artifacts.
  --help, -h          Show this help text.

Environment:
  CI_SKIP_BROWSER_BOOTSTRAP=1  Skip Chrome/bootstrap install for non-UI runs.
EOF
}

list_suites() {
  cat <<'EOF'
Available suites:
  competition_core       Base, tournament, scheduling, results, and standings critical path
  portal_public_ops      Portal ownership, public routes, compliance, standings, and venue-facing flows
  finance_reporting      Finance bridge and reporting coverage
  rosters_readiness_guard Participant readiness regression guard with discovery enforcement
  release_surfaces       Broader portal/public, match-day, compliance, and notification release verification
  people_rosters_rules   People, rosters, rules, and officiating modules
  ops_and_notifications  Discipline, governance, notifications, import_tools, and demo modules
EOF
}

resolve_suite_modules() {
  case "$1" in
    competition_core)
      cat <<'EOF'
sports_federation_base
sports_federation_tournament
sports_federation_competition_core
sports_federation_registration
sports_federation_format
sports_federation_calendar
sports_federation_scheduling
sports_federation_schedule_approval
sports_federation_matchday
sports_federation_result_control
sports_federation_standings
EOF
      ;;
    portal_public_ops)
      cat <<'EOF'
sports_federation_portal
sports_federation_public_site
sports_federation_compliance
sports_federation_standings
sports_federation_venues
EOF
      ;;
    finance_reporting)
      cat <<'EOF'
sports_federation_finance_bridge
sports_federation_reporting
EOF
      ;;
    rosters_readiness_guard)
      cat <<'EOF'
sports_federation_rosters
EOF
      ;;
    release_surfaces)
      cat <<'EOF'
sports_federation_portal
sports_federation_public_site
sports_federation_compliance
sports_federation_rosters
sports_federation_officiating
sports_federation_result_control
sports_federation_notifications
sports_federation_discipline
sports_federation_standings
sports_federation_venues
EOF
      ;;
    people_rosters_rules)
      cat <<'EOF'
sports_federation_people
sports_federation_rosters
sports_federation_rules
sports_federation_officiating
EOF
      ;;
    ops_and_notifications)
      cat <<'EOF'
sports_federation_discipline
sports_federation_governance
sports_federation_notifications
sports_federation_import_tools
sports_federation_demo
EOF
      ;;
    *)
      return 1
      ;;
  esac
}

for arg in "$@"; do
  case "$arg" in
    --list-suites)
      list_suites
      exit 0
      ;;
    --help|-h)
      usage
      exit 0
      ;;
  esac
done

if [[ -f "$ENV_FILE" ]]; then
  LOADED_ENV_FILE="$ENV_FILE"
elif [[ -f "$EXAMPLE_ENV_FILE" ]]; then
  LOADED_ENV_FILE="$EXAMPLE_ENV_FILE"
else
  echo "Missing CI environment file. Create $ENV_FILE from $EXAMPLE_ENV_FILE." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$LOADED_ENV_FILE"
set +a

# A CRLF-formatted env file leaves a trailing carriage return in values when
# sourced by Bash. PostgreSQL accepts that byte as part of the password, while
# Odoo's config parser trims it, producing an otherwise invisible mismatch.
# Normalize all CI connection settings before Compose or the Odoo config sees
# them.
CI_PROJECT_NAME="${CI_PROJECT_NAME//$'\r'/}"
CI_POSTGRES_USER="${CI_POSTGRES_USER//$'\r'/}"
CI_POSTGRES_PASSWORD="${CI_POSTGRES_PASSWORD//$'\r'/}"
CI_POSTGRES_DB="${CI_POSTGRES_DB//$'\r'/}"
CI_ODOO_DB_NAME="${CI_ODOO_DB_NAME//$'\r'/}"
CI_ODOO_DB_HOST="${CI_ODOO_DB_HOST//$'\r'/}"
CI_ODOO_DB_PORT="${CI_ODOO_DB_PORT//$'\r'/}"

: "${CI_PROJECT_NAME:=sf_ci}"
: "${CI_POSTGRES_USER:=odoo}"
: "${CI_POSTGRES_PASSWORD:=change_me}"
: "${CI_POSTGRES_DB:=postgres}"
: "${CI_ODOO_DB_NAME:=odoo_ci_test}"
: "${CI_ODOO_DB_HOST:=ci-db}"
: "${CI_ODOO_DB_PORT:=5432}"
: "${CI_LOG_RETENTION_RUNS:=30}"
: "${CI_SKIP_BROWSER_BOOTSTRAP:=0}"
export CI_PROJECT_NAME CI_POSTGRES_USER CI_POSTGRES_PASSWORD CI_POSTGRES_DB \
  CI_ODOO_DB_NAME CI_ODOO_DB_HOST CI_ODOO_DB_PORT CI_LOG_RETENTION_RUNS \
  CI_SKIP_BROWSER_BOOTSTRAP

PROJECT_NAME="$CI_PROJECT_NAME"

cat > "$GENERATED_CONF" <<EOF
[options]
db_host = ${CI_ODOO_DB_HOST}
db_port = ${CI_ODOO_DB_PORT}
db_user = ${CI_POSTGRES_USER}
db_password = ${CI_POSTGRES_PASSWORD}

addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons
data_dir = /var/lib/odoo

list_db = False
without_demo = True
log_level = info
EOF

# ── Topological install order (dependency-safe) ──────────────────────
ALL_MODULES=(
  sports_federation_base
  sports_federation_rules
  sports_federation_people
  sports_federation_tournament
  sports_federation_competition_core
  sports_federation_standings
  sports_federation_venues
  sports_federation_result_control
  sports_federation_portal
  sports_federation_rosters
  sports_federation_registration
  sports_federation_format
  sports_federation_calendar
  sports_federation_scheduling
  sports_federation_schedule_approval
  sports_federation_matchday
  sports_federation_officiating
  sports_federation_discipline
  sports_federation_governance
  sports_federation_notifications
  sports_federation_import_tools
  sports_federation_finance_bridge
  sports_federation_compliance
  sports_federation_public_site
  sports_federation_reporting
  sports_federation_demo
)

is_known_module() {
  local candidate="$1"
  local module
  for module in "${ALL_MODULES[@]}"; do
    if [[ "$module" == "$candidate" ]]; then
      return 0
    fi
  done
  return 1
}

contains_module() {
  local candidate="$1"
  shift || true
  local module
  for module in "$@"; do
    if [[ "$module" == "$candidate" ]]; then
      return 0
    fi
  done
  return 1
}

# ── CLI parsing ──────────────────────────────────────────────────────
MODULES=()
SUITES=()
FRONTEND_MODULES=()
CUSTOM_TEST_TAGS=""
REQUIRE_POST_TESTS=0
KEEP=false
KEEP_ON_FAILURE=false
FRONTEND_MODE=false
AFFECTED_FROM=""
INCLUDE_DEPENDENTS=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --module|-m)
      [[ $# -ge 2 ]] || { echo "Missing value for $1" >&2; usage >&2; exit 1; }
      MODULES+=("$2")
      shift 2
      ;;
    --suite|-s)
      [[ $# -ge 2 ]] || { echo "Missing value for $1" >&2; usage >&2; exit 1; }
      SUITES+=("$2")
      shift 2
      ;;
    --frontend-module)
      [[ $# -ge 2 ]] || { echo "Missing value for $1" >&2; usage >&2; exit 1; }
      FRONTEND_MODULES+=("$2")
      FRONTEND_MODE=true
      shift 2
      ;;
    --affected-from)
      [[ $# -ge 2 ]] || { echo "Missing value for $1" >&2; usage >&2; exit 1; }
      AFFECTED_FROM="$2"
      shift 2
      ;;
    --include-dependents)
      INCLUDE_DEPENDENTS=true
      shift
      ;;
    --test-tags)
      [[ $# -ge 2 ]] || { echo "Missing value for $1" >&2; usage >&2; exit 1; }
      CUSTOM_TEST_TAGS="$2"
      shift 2
      ;;
    --require-post-tests)
      [[ $# -ge 2 ]] || { echo "Missing value for $1" >&2; usage >&2; exit 1; }
      REQUIRE_POST_TESTS="$2"
      shift 2
      ;;
    --list-suites)
      list_suites
      exit 0
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --keep|-k)
      KEEP=true
      shift
      ;;
    --keep-on-failure)
      KEEP_ON_FAILURE=true
      shift
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$INCLUDE_DEPENDENTS" == "true" && -z "$AFFECTED_FROM" ]]; then
  echo "--include-dependents requires --affected-from" >&2
  exit 1
fi

if ! [[ "$REQUIRE_POST_TESTS" =~ ^[0-9]+$ ]]; then
  echo "--require-post-tests must be a non-negative integer" >&2
  exit 1
fi

if [[ ${#SUITES[@]} -gt 0 ]]; then
  for suite in "${SUITES[@]}"; do
    if ! suite_modules="$(resolve_suite_modules "$suite")"; then
      echo "Unknown suite: $suite" >&2
      list_suites >&2
      exit 1
    fi
    while IFS= read -r module; do
      MODULES+=("$module")
    done <<< "$suite_modules"
  done
fi

if [[ "$AFFECTED_FROM" != "" ]]; then
  SCOPE_ARGS=(--affected-from "$AFFECTED_FROM")
  if [[ "$INCLUDE_DEPENDENTS" == "true" ]]; then
    SCOPE_ARGS+=(--include-dependents)
  fi
  mapfile -t AFFECTED_MODULES < <(
    python3 "$SCRIPT_DIR/resolve_ci_scope.py" "${SCOPE_ARGS[@]}"
  )
  if [[ ${#AFFECTED_MODULES[@]} -eq 0 ]]; then
    echo "No sports federation modules changed since $AFFECTED_FROM" >&2
    exit 1
  fi
  MODULES+=("${AFFECTED_MODULES[@]}")
fi

if [[ ${#FRONTEND_MODULES[@]} -gt 0 ]]; then
  if [[ -n "$CUSTOM_TEST_TAGS" ]]; then
    echo "--frontend-module cannot be combined with --test-tags" >&2
    exit 1
  fi
  MODULES+=("${FRONTEND_MODULES[@]}")
  CUSTOM_TEST_TAGS="sf_frontend_http,sf_frontend_accessibility,sf_frontend_mobile"
  REQUIRE_POST_TESTS=1
fi

for suite in "${SUITES[@]}"; do
  case "$suite" in
    competition_core|portal_public_ops|finance_reporting|release_surfaces|people_rosters_rules|ops_and_notifications)
      if (( REQUIRE_POST_TESTS < 1 )); then
        REQUIRE_POST_TESTS=1
      fi
      ;;
  esac
  if [[ "$suite" == "rosters_readiness_guard" ]]; then
    if [[ -z "$CUSTOM_TEST_TAGS" ]]; then
      CUSTOM_TEST_TAGS="sf_rosters_participant_readiness"
    fi
    if (( REQUIRE_POST_TESTS < 1 )); then
      REQUIRE_POST_TESTS=1
    fi
  fi
done

if [[ ${#MODULES[@]} -eq 0 ]]; then
  MODULES=("${ALL_MODULES[@]}")
fi

UNIQUE_MODULES=()
for module in "${MODULES[@]}"; do
  if ! is_known_module "$module"; then
    echo "Unknown module: $module" >&2
    exit 1
  fi
  if ! contains_module "$module" "${UNIQUE_MODULES[@]}"; then
    UNIQUE_MODULES+=("$module")
  fi
done
MODULES=("${UNIQUE_MODULES[@]}")

# Restore dependency-safe install order after combining suites and dynamic scopes.
ORDERED_MODULES=()
for module in "${ALL_MODULES[@]}"; do
  if contains_module "$module" "${MODULES[@]}"; then
    ORDERED_MODULES+=("$module")
  fi
done
MODULES=("${ORDERED_MODULES[@]}")

MODULE_CSV=$(IFS=,; echo "${MODULES[*]}")
SUITE_CSV=$(IFS=,; echo "${SUITES[*]}")

# ── Log directory ────────────────────────────────────────────────────
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$SCRIPT_DIR/logs/$TIMESTAMP"
mkdir -p "$LOG_DIR"

if [[ "$KEEP_ON_FAILURE" == "true" ]]; then
  PROJECT_NAME="${CI_PROJECT_NAME}_${TIMESTAMP}"
fi

RAW_LOG="$LOG_DIR/raw.log"
SUMMARY_LOG="$LOG_DIR/summary.log"
ERRORS_LOG="$LOG_DIR/errors.log"
TEST_FAILURES_LOG="$LOG_DIR/test_failures.log"
EXPECTED_DIAGNOSTICS_LOG="$LOG_DIR/expected_diagnostics.log"
INFRASTRUCTURE_LOG="$LOG_DIR/infrastructure.log"
FULL_LOG="$LOG_DIR/full.log"

echo "=== SF CI Run – $TIMESTAMP ===" | tee "$SUMMARY_LOG"
echo "Modules: $MODULE_CSV" | tee -a "$SUMMARY_LOG"
if [[ ${#SUITES[@]} -gt 0 ]]; then
  echo "Suites:  $SUITE_CSV" | tee -a "$SUMMARY_LOG"
fi
echo "Config:  $LOADED_ENV_FILE" | tee -a "$SUMMARY_LOG"
echo "Logs:    $LOG_DIR" | tee -a "$SUMMARY_LOG"
echo "Project: $PROJECT_NAME" | tee -a "$SUMMARY_LOG"
echo "────────────────────────────────────────────" | tee -a "$SUMMARY_LOG"

# ── Bring up isolated environment ────────────────────────────────────
echo "[CI] Starting containers …"
# Recreate the database container so credentials from a previous interrupted
# run cannot survive under a reused Compose project name.
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" up -d --force-recreate ci-db
echo "[CI] Waiting for Postgres to be healthy …"
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" up -d --wait ci-db

# The regular socket-based psql checks below do not verify the configured
# password. Prove TCP password authentication before starting Odoo so a
# credential mismatch is reported as infrastructure failure immediately.
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" exec -T \
  -e PGPASSWORD="$CI_POSTGRES_PASSWORD" ci-db \
  psql -h 127.0.0.1 -U "$CI_POSTGRES_USER" -d "$CI_POSTGRES_DB" \
  -v ON_ERROR_STOP=1 -c "SELECT 1" >/dev/null

# Create the test database
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" exec -T ci-db \
  psql -U "$CI_POSTGRES_USER" -d "$CI_POSTGRES_DB" -c "SELECT 1 FROM pg_database WHERE datname='$CI_ODOO_DB_NAME'" \
  | grep -q 1 || \
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" exec -T ci-db \
  psql -U "$CI_POSTGRES_USER" -d "$CI_POSTGRES_DB" -c "CREATE DATABASE \"$CI_ODOO_DB_NAME\" OWNER \"$CI_POSTGRES_USER\";"

# Apply integration envs (if any) into Odoo system parameters so tests
# that rely on configured providers can read them from ir.config_parameter.
echo "[CI] Applying integration envs to Odoo..."
bash "$SCRIPT_DIR/apply_env_to_ir_config.sh" "$PROJECT_NAME" "$COMPOSE_FILE" "$LOADED_ENV_FILE" "$GENERATED_CONF" || echo "[CI] apply_env_to_ir_config.sh failed; continuing"

# ── Run tests ────────────────────────────────────────────────────────
echo "[CI] Installing & testing: $MODULE_CSV"
EXIT_CODE=0

# Build test tags to only run federation module tests (skip base Odoo tests)
TEST_TAGS=""
for mod in "${MODULES[@]}"; do
  if [[ -n "$TEST_TAGS" ]]; then
    TEST_TAGS="$TEST_TAGS,$mod"
  else
    TEST_TAGS="$mod"
  fi
done
if [[ -n "$CUSTOM_TEST_TAGS" ]]; then
  TEST_TAGS="$CUSTOM_TEST_TAGS"
fi

FRONTEND_STATIC_EXIT=0
if [[ "$FRONTEND_MODE" == "true" ]]; then
  FRONTEND_STATIC_LOG="$LOG_DIR/frontend_static.log"
  NODE_BIN=""
  for candidate in /usr/bin/node /usr/local/bin/node /usr/bin/nodejs /usr/local/bin/nodejs; do
    if [[ -x "$candidate" ]]; then
      NODE_BIN="$candidate"
      break
    fi
  done
  if [[ -z "$NODE_BIN" ]]; then
    NODE_BIN="$(command -v node || command -v nodejs || true)"
  fi
  : > "$FRONTEND_STATIC_LOG"
  echo "[CI] Frontend-only static checks" | tee -a "$FRONTEND_STATIC_LOG"
  for module in "${MODULES[@]}"; do
    while IFS= read -r js_path; do
      if [[ -n "$NODE_BIN" ]]; then
        "$NODE_BIN" --check "$js_path" >> "$FRONTEND_STATIC_LOG" 2>&1 || FRONTEND_STATIC_EXIT=1
      else
        echo "WARNING: node or nodejs unavailable; skipped JavaScript syntax check for $js_path" >> "$FRONTEND_STATIC_LOG"
      fi
    done < <(find "$SCRIPT_DIR/../$module" -type f -name '*.js' -not -path '*/static/lib/*' -print)
    if ! python3 - "$SCRIPT_DIR/../$module" >> "$FRONTEND_STATIC_LOG" 2>&1 <<'PY'
import pathlib
import sys
import xml.etree.ElementTree as ET

root = pathlib.Path(sys.argv[1])
for path in root.rglob("*.xml"):
    ET.parse(path)
print(f"frontend static checks passed: {root.name}")
PY
    then
      FRONTEND_STATIC_EXIT=1
    fi
  done
  cat "$FRONTEND_STATIC_LOG" | tee -a "$SUMMARY_LOG"
  if (( FRONTEND_STATIC_EXIT != 0 )); then
    echo "[CI] Frontend static checks failed" | tee -a "$SUMMARY_LOG"
  fi
fi

DEMO_OPTION=""
if contains_module "sports_federation_demo" "${MODULES[@]}"; then
  DEMO_OPTION="--without-demo=False"
fi

TEST_CONTAINER_CMD=$(cat <<EOF
python3 -m pip show websocket-client >/dev/null 2>&1 || python3 -m pip install --break-system-packages --no-cache-dir websocket-client==1.8.0
if [ "$CI_SKIP_BROWSER_BOOTSTRAP" != "1" ]; then
  if ! command -v google-chrome >/dev/null 2>&1 && ! command -v google-chrome-stable >/dev/null 2>&1 && ! command -v chromium >/dev/null 2>&1; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y wget
    wget -q -O /tmp/google-chrome-stable_current_amd64.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    DEBIAN_FRONTEND=noninteractive apt-get install -y /tmp/google-chrome-stable_current_amd64.deb
  fi
  if command -v google-chrome-stable >/dev/null 2>&1; then
    ln -sf "\$(command -v google-chrome-stable)" /usr/local/bin/chromium-browser
  elif command -v google-chrome >/dev/null 2>&1; then
    ln -sf "\$(command -v google-chrome)" /usr/local/bin/chromium-browser
  fi
fi
exec odoo --stop-after-init --test-enable --test-tags="$TEST_TAGS" $DEMO_OPTION -d "$CI_ODOO_DB_NAME" -i "$MODULE_CSV"
EOF
)

RUN_CONTAINER_ARGS=()
if [[ "$KEEP_ON_FAILURE" != "true" ]]; then
  RUN_CONTAINER_ARGS=(--rm)
fi
# Compose has no --no-rm flag; omitting --rm retains the one-off Odoo
# container so its filestore and generated configuration remain inspectable.

docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" run "${RUN_CONTAINER_ARGS[@]}" \
  ci-odoo \
  sh -lc "$TEST_CONTAINER_CMD" \
  2>&1 | tee "$RAW_LOG" || EXIT_CODE=$?

if (( FRONTEND_STATIC_EXIT != 0 )); then
  EXIT_CODE=1
fi

cp "$RAW_LOG" "$FULL_LOG"
python3 "$SCRIPT_DIR/parse_ci_logs.py" "$RAW_LOG" "$LOG_DIR" | tee -a "$SUMMARY_LOG" || true

# ── Parse results ────────────────────────────────────────────────────
TEST_RESULT_LINE=$(grep -F "odoo.tests.result:" "$RAW_LOG" | tail -1 || true)
POST_TESTS_LINE=$(grep -E "[0-9]+ post-tests in" "$RAW_LOG" | tail -1 || true)
TESTS_TOTAL="n/a"
TESTS_PASSED="n/a"
TESTS_FAILED="n/a"
TESTS_ERRORS="n/a"
DIAGNOSTIC_COUNT="n/a"
POST_TESTS_RUN="n/a"

if [[ -n "$TEST_RESULT_LINE" ]] && [[ "$TEST_RESULT_LINE" =~ :[[:space:]]*([0-9]+)[[:space:]]+failed,[[:space:]]*([0-9]+)[[:space:]]+error\(s\)[[:space:]]+of[[:space:]]+([0-9]+)[[:space:]]+tests ]]; then
  TESTS_FAILED="${BASH_REMATCH[1]}"
  TESTS_ERRORS="${BASH_REMATCH[2]}"
  TESTS_TOTAL="${BASH_REMATCH[3]}"
  TESTS_PASSED=$((TESTS_TOTAL - TESTS_FAILED - TESTS_ERRORS))
fi

if [[ -n "$POST_TESTS_LINE" ]] && [[ "$POST_TESTS_LINE" =~ ([0-9]+)[[:space:]]+post-tests[[:space:]]+in ]]; then
  POST_TESTS_RUN="${BASH_REMATCH[1]}"
fi

: > "$ERRORS_LOG"
if [[ "$TESTS_FAILED" != "0" || "$TESTS_ERRORS" != "0" || $EXIT_CODE -ne 0 ]]; then
  grep -iE "(^FAIL:|^ERROR:|FAILED|CRITICAL|Traceback|AssertionError|raise .*Error)" "$RAW_LOG" > "$ERRORS_LOG" 2>/dev/null || true
fi

if [[ -s "$ERRORS_LOG" ]]; then
  DIAGNOSTIC_COUNT=$(wc -l < "$ERRORS_LOG" | tr -d ' ')
elif [[ "$TESTS_TOTAL" == "n/a" ]]; then
  grep -iE "(FAIL|ERROR|CRITICAL|Traceback|raise .*Error)" "$RAW_LOG" > "$ERRORS_LOG" 2>/dev/null || true
  DIAGNOSTIC_COUNT=$(wc -l < "$ERRORS_LOG" | tr -d ' ')
fi

{
  echo ""
  echo "════════════════════════════════════════════"
  echo "  RESULTS"
  echo "════════════════════════════════════════════"
  echo "  Exit code:     $EXIT_CODE"
  echo "  Tests run:     $TESTS_TOTAL"
  echo "  Tests passed:  $TESTS_PASSED"
  echo "  Tests failed:  $TESTS_FAILED"
  echo "  Test errors:   $TESTS_ERRORS"
  echo "  Post-tests:    $POST_TESTS_RUN"
  if [[ "$DIAGNOSTIC_COUNT" != "n/a" ]]; then
    echo "  Diagnostics:   $DIAGNOSTIC_COUNT"
  fi
  echo "  Failure log:   $TEST_FAILURES_LOG"
  echo "  Expected log:  $EXPECTED_DIAGNOSTICS_LOG"
  echo "  Infrastructure: $INFRASTRUCTURE_LOG"
  echo "  Full log:      $FULL_LOG"
  echo "════════════════════════════════════════════"
} | tee -a "$SUMMARY_LOG"

if (( REQUIRE_POST_TESTS > 0 )); then
  POST_TESTS_NUM=0
  if [[ "$POST_TESTS_RUN" =~ ^[0-9]+$ ]]; then
    POST_TESTS_NUM="$POST_TESTS_RUN"
  fi
  if (( POST_TESTS_NUM < REQUIRE_POST_TESTS )); then
    EXIT_CODE=1
    {
      echo "[CI] post-test discovery gate failed"
      echo "[CI] required post-tests: $REQUIRE_POST_TESTS"
      echo "[CI] discovered post-tests: $POST_TESTS_NUM"
      echo "[CI] test tags: $TEST_TAGS"
    } | tee -a "$ERRORS_LOG" >&2
  fi
fi

if (( EXIT_CODE != 0 )); then
  echo "  Final exit code: $EXIT_CODE" | tee -a "$SUMMARY_LOG"
fi

if [[ $EXIT_CODE -ne 0 ]]; then
  echo ""
  echo "[CI] ❌ TESTS FAILED — see $ERRORS_LOG"
  echo "Last 30 lines of errors:"
  tail -30 "$ERRORS_LOG"
fi

write_retention_commands() {
  local commands="$LOG_DIR/retained-container-commands.sh"
  cat > "$commands" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export CI_POSTGRES_USER='$CI_POSTGRES_USER'
export CI_POSTGRES_PASSWORD='$CI_POSTGRES_PASSWORD'
export CI_POSTGRES_DB='$CI_POSTGRES_DB'
export CI_ODOO_DB_HOST='$CI_ODOO_DB_HOST'
export CI_ODOO_DB_PORT='$CI_ODOO_DB_PORT'
PROJECT_NAME='$PROJECT_NAME'
COMPOSE_FILE='$COMPOSE_FILE'
DB_NAME='$CI_ODOO_DB_NAME'
docker compose -p "\$PROJECT_NAME" -f "\$COMPOSE_FILE" ps
docker compose -p "\$PROJECT_NAME" -f "\$COMPOSE_FILE" logs --tail=200 ci-odoo
docker compose -p "\$PROJECT_NAME" -f "\$COMPOSE_FILE" exec -T ci-db psql -U '$CI_POSTGRES_USER' -d "\$DB_NAME" -c '\\dt'
docker compose -p "\$PROJECT_NAME" -f "\$COMPOSE_FILE" exec -T ci-odoo find /var/lib/odoo/filestore -maxdepth 2 -type f | head -100
docker cp "\$(docker compose -p \"\$PROJECT_NAME\" -f \"\$COMPOSE_FILE\" ps -q ci-odoo):/var/lib/odoo/filestore" '$LOG_DIR/filestore'
docker cp "\$(docker compose -p \"\$PROJECT_NAME\" -f \"\$COMPOSE_FILE\" ps -q ci-odoo):/etc/odoo/odoo.conf" '$LOG_DIR/odoo.conf.retained'
docker compose -p "\$PROJECT_NAME" -f "\$COMPOSE_FILE" down -v --remove-orphans
EOF
  chmod +x "$commands"
  echo "[CI] Retained-container commands: $commands" | tee -a "$SUMMARY_LOG"
}

# ── Cleanup ──────────────────────────────────────────────────────────
if [[ "$KEEP" == "false" && ! ( "$KEEP_ON_FAILURE" == "true" && $EXIT_CODE -ne 0 ) ]]; then
  echo ""
  echo "[CI] Tearing down containers …"
  if [[ "$KEEP_ON_FAILURE" == "true" ]]; then
    docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" rm -f ci-odoo 2>/dev/null || true
  fi
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
  if [[ -f "$GENERATED_CONF" ]]; then
    rm -f "$GENERATED_CONF"
  fi
else
  echo ""
  if [[ "$KEEP_ON_FAILURE" == "true" && $EXIT_CODE -ne 0 ]]; then
    write_retention_commands
    echo "[CI] --keep-on-failure: retained project $PROJECT_NAME"
  else
    echo "[CI] --keep: containers left running (project: $PROJECT_NAME)"
    echo "     To stop: docker compose -p $PROJECT_NAME -f $COMPOSE_FILE down -v"
  fi
fi

if [[ -x "$SCRIPT_DIR/prune_ci_logs.sh" ]]; then
  bash "$SCRIPT_DIR/prune_ci_logs.sh" "$CI_LOG_RETENTION_RUNS" >/dev/null 2>&1 || true
fi

exit "$EXIT_CODE"

python ci/check_public_competition_contract.py
