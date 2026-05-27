#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
# Sports Federation CI – run Odoo module tests in an isolated container.
#
# Usage:
#   bash ci/run_tests.sh                          # test all modules
#   bash ci/run_tests.sh --module sports_federation_base
#   bash ci/run_tests.sh --suite portal_public_ops
#   bash ci/run_tests.sh --module sports_federation_rosters --test-tags sf_rosters_participant_readiness --require-post-tests 1
#   bash ci/run_tests.sh --list-suites
#   bash ci/run_tests.sh --keep                  # keep containers for debugging
#
# Requirements: docker compose v2
# ──────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.ci.yaml"
ENV_FILE="$SCRIPT_DIR/.env"
EXAMPLE_ENV_FILE="$SCRIPT_DIR/.env.example"
GENERATED_CONF="$SCRIPT_DIR/odoo-ci.generated.runtime.conf"

if [[ -d "$GENERATED_CONF" ]]; then
  GENERATED_CONF="$(mktemp "$SCRIPT_DIR/odoo-ci.generated.conf.XXXXXX")"
fi

usage() {
  cat <<'EOF'
Usage:
  bash ci/run_tests.sh
  bash ci/run_tests.sh --module sports_federation_base
  bash ci/run_tests.sh --suite competition_core
  bash ci/run_tests.sh --suite portal_public_ops --keep
  bash ci/run_tests.sh --module sports_federation_rosters --test-tags sf_rosters_participant_readiness --require-post-tests 1
  bash ci/run_tests.sh --list-suites

Options:
  --module, -m        Add a module to the install/test list. Repeatable.
  --suite, -s         Add a named test suite. Repeatable.
  --test-tags         Override Odoo --test-tags expression used for discovery.
  --require-post-tests Fail if discovered post-tests are below the provided minimum.
  --list-suites       Print the available named suites.
  --keep, -k          Leave the Docker Compose stack running after the run.
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
sports_federation_competition_engine
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

: "${CI_PROJECT_NAME:=sf_ci}"
: "${CI_POSTGRES_USER:=odoo}"
: "${CI_POSTGRES_PASSWORD:=change_me}"
: "${CI_POSTGRES_DB:=postgres}"
: "${CI_ODOO_DB_NAME:=odoo_ci_test}"
: "${CI_ODOO_DB_HOST:=ci-db}"
: "${CI_ODOO_DB_PORT:=5432}"
: "${CI_LOG_RETENTION_RUNS:=30}"
: "${CI_SKIP_BROWSER_BOOTSTRAP:=0}"

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
  sports_federation_standings
  sports_federation_venues
  sports_federation_result_control
  sports_federation_portal
  sports_federation_rosters
  sports_federation_competition_engine
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
CUSTOM_TEST_TAGS=""
REQUIRE_POST_TESTS=0
KEEP=false
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
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

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

MODULE_CSV=$(IFS=,; echo "${MODULES[*]}")
SUITE_CSV=$(IFS=,; echo "${SUITES[*]}")

# ── Log directory ────────────────────────────────────────────────────
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$SCRIPT_DIR/logs/$TIMESTAMP"
mkdir -p "$LOG_DIR"

RAW_LOG="$LOG_DIR/raw.log"
SUMMARY_LOG="$LOG_DIR/summary.log"
ERRORS_LOG="$LOG_DIR/errors.log"

echo "=== SF CI Run – $TIMESTAMP ===" | tee "$SUMMARY_LOG"
echo "Modules: $MODULE_CSV" | tee -a "$SUMMARY_LOG"
if [[ ${#SUITES[@]} -gt 0 ]]; then
  echo "Suites:  $SUITE_CSV" | tee -a "$SUMMARY_LOG"
fi
echo "Config:  $LOADED_ENV_FILE" | tee -a "$SUMMARY_LOG"
echo "Logs:    $LOG_DIR" | tee -a "$SUMMARY_LOG"
echo "────────────────────────────────────────────" | tee -a "$SUMMARY_LOG"

# ── Bring up isolated environment ────────────────────────────────────
echo "[CI] Starting containers …"
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" up -d ci-db
echo "[CI] Waiting for Postgres to be healthy …"
docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" up -d --wait ci-db

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
exec odoo --stop-after-init --test-enable --test-tags="$TEST_TAGS" -d "$CI_ODOO_DB_NAME" -i "$MODULE_CSV"
EOF
)

docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" run --rm \
  ci-odoo \
  sh -lc "$TEST_CONTAINER_CMD" \
  2>&1 | tee "$RAW_LOG" || EXIT_CODE=$?

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

if [[ $EXIT_CODE -ne 0 ]]; then
  echo ""
  echo "[CI] ❌ TESTS FAILED — see $ERRORS_LOG"
  echo "Last 30 lines of errors:"
  tail -30 "$ERRORS_LOG"
fi

# ── Cleanup ──────────────────────────────────────────────────────────
if [[ "$KEEP" == "false" ]]; then
  echo ""
  echo "[CI] Tearing down containers …"
  docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
  if [[ -f "$GENERATED_CONF" ]]; then
    rm -f "$GENERATED_CONF"
  fi
else
  echo ""
  echo "[CI] --keep: containers left running (project: $PROJECT_NAME)"
  echo "     To stop: docker compose -p $PROJECT_NAME -f $COMPOSE_FILE down -v"
fi

if [[ -x "$SCRIPT_DIR/prune_ci_logs.sh" ]]; then
  bash "$SCRIPT_DIR/prune_ci_logs.sh" "$CI_LOG_RETENTION_RUNS" >/dev/null 2>&1 || true
fi

exit "$EXIT_CODE"
