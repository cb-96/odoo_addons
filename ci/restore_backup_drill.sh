#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash addons/ci/restore_backup_drill.sh --backup-dir BACKUP_DIR --target-db DB_NAME [options]

Options:
  --backup-dir PATH         Backup directory name or path to restore from.
  --target-db DB_NAME       Target PostgreSQL database used for the restore drill.
  --compose-file PATH       Compose file to use (default: ../docker-compose.yaml).
  --project-name NAME       Optional docker compose project name.
  --db-service NAME         Compose database service name (default: db).
  --db-user NAME            PostgreSQL user for psql/pg_restore (default: odoo).
  --backup-root PATH        Backup root directory (default: ../backups).
  --filestore-root PATH     Filestore root directory (default: ../odoo-data/filestore).
  --report-file PATH        Optional report file path (default: <backup-dir>/restore_drill_<target-db>.txt).
  --skip-filestore          Skip restoring the filestore archive.
  --dry-run                 Print the resolved restore plan and exit.
  --yes, -y                 Skip the confirmation prompt.
  --help, -h                Show this help message.

Examples:
  bash addons/ci/restore_backup_drill.sh --backup-dir 2026-04-15_191410 --target-db odoo_restore_drill --dry-run
  bash addons/ci/restore_backup_drill.sh --backup-dir ../backups/2026-04-15_191410 --target-db odoo_restore_drill

Notes:
  - The script expects a backup directory created by ./scripts/upgrade_sports_federation.sh.
  - The target database is dropped and recreated before the restore drill runs.
EOF
}

log() {
  printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

die() {
  echo "Error: $*" >&2
  exit 1
}

trim() {
  local value="$1"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  printf '%s' "$value"
}

resolve_path() {
  local value="$1"
  if [[ "$value" = /* ]]; then
    printf '%s' "$value"
    return 0
  fi
  if [[ -d "$value" || -f "$value" ]]; then
    printf '%s' "$value"
    return 0
  fi
  printf '%s' "$BACKUP_ROOT/$value"
}

find_single_file() {
  local dir_path="$1"
  local pattern="$2"
  local label="$3"
  local matches=()

  shopt -s nullglob
  matches=("$dir_path"/$pattern)
  shopt -u nullglob

  if [[ ${#matches[@]} -eq 0 ]]; then
    die "No $label matching '$pattern' found in $dir_path"
  fi
  if [[ ${#matches[@]} -gt 1 ]]; then
    die "Expected one $label matching '$pattern' in $dir_path, found ${#matches[@]}"
  fi
  printf '%s' "${matches[0]}"
}

find_optional_file() {
  local dir_path="$1"
  local pattern="$2"
  local label="$3"
  local matches=()

  shopt -s nullglob
  matches=("$dir_path"/$pattern)
  shopt -u nullglob

  if [[ ${#matches[@]} -eq 0 ]]; then
    return 0
  fi
  if [[ ${#matches[@]} -gt 1 ]]; then
    die "Expected at most one $label matching '$pattern' in $dir_path, found ${#matches[@]}"
  fi
  printf '%s' "${matches[0]}"
}

sql_literal_list() {
  local module=""
  local literals=()

  for module in "$@"; do
    literals+=("'${module//\'/\'\'}'")
  done

  local IFS=,
  printf '%s' "${literals[*]}"
}

restore_filestore_archive() {
  local archive_path="$1"
  local target_db="$2"
  local temp_dir=""
  local extracted_entries=()

  temp_dir="$(mktemp -d)"
  tar -xzf "$archive_path" -C "$temp_dir"

  shopt -s nullglob
  extracted_entries=("$temp_dir"/*)
  shopt -u nullglob

  if [[ ${#extracted_entries[@]} -ne 1 || ! -d "${extracted_entries[0]}" ]]; then
    rm -rf "$temp_dir"
    die "Expected the filestore archive to contain exactly one top-level directory"
  fi

  mkdir -p "$FILESTORE_ROOT"
  rm -rf "$FILESTORE_ROOT/$target_db"
  mv "${extracted_entries[0]}" "$FILESTORE_ROOT/$target_db"
  rm -rf "$temp_dir"
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORKSPACE_ROOT="$(cd "$REPO_ROOT/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$WORKSPACE_ROOT/docker-compose.yaml}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-}"
DB_SERVICE="${DB_SERVICE:-db}"
DB_USER="${DB_USER:-odoo}"
BACKUP_ROOT="${BACKUP_ROOT:-$WORKSPACE_ROOT/backups}"
FILESTORE_ROOT="${FILESTORE_ROOT:-$WORKSPACE_ROOT/odoo-data/filestore}"
BACKUP_DIR=""
TARGET_DB=""
REPORT_FILE=""
SKIP_FILESTORE=false
DRY_RUN=false
AUTO_CONFIRM=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backup-dir)
      [[ $# -ge 2 ]] || die "Missing value for $1"
      BACKUP_DIR="$2"
      shift 2
      ;;
    --target-db)
      [[ $# -ge 2 ]] || die "Missing value for $1"
      TARGET_DB="$2"
      shift 2
      ;;
    --compose-file)
      [[ $# -ge 2 ]] || die "Missing value for $1"
      COMPOSE_FILE="$2"
      shift 2
      ;;
    --project-name)
      [[ $# -ge 2 ]] || die "Missing value for $1"
      COMPOSE_PROJECT_NAME="$2"
      shift 2
      ;;
    --db-service)
      [[ $# -ge 2 ]] || die "Missing value for $1"
      DB_SERVICE="$2"
      shift 2
      ;;
    --db-user)
      [[ $# -ge 2 ]] || die "Missing value for $1"
      DB_USER="$2"
      shift 2
      ;;
    --backup-root)
      [[ $# -ge 2 ]] || die "Missing value for $1"
      BACKUP_ROOT="$2"
      shift 2
      ;;
    --filestore-root)
      [[ $# -ge 2 ]] || die "Missing value for $1"
      FILESTORE_ROOT="$2"
      shift 2
      ;;
    --report-file)
      [[ $# -ge 2 ]] || die "Missing value for $1"
      REPORT_FILE="$2"
      shift 2
      ;;
    --skip-filestore)
      SKIP_FILESTORE=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --yes|-y)
      AUTO_CONFIRM=true
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

[[ -n "$BACKUP_DIR" ]] || die "Missing --backup-dir BACKUP_DIR"
[[ -n "$TARGET_DB" ]] || die "Missing --target-db DB_NAME"
[[ -f "$COMPOSE_FILE" ]] || die "Compose file not found: $COMPOSE_FILE"

command -v docker >/dev/null 2>&1 || die "docker is required but not found in PATH"
docker compose version >/dev/null 2>&1 || die "docker compose is required but not available"

BACKUP_DIR="$(resolve_path "$BACKUP_DIR")"
[[ -d "$BACKUP_DIR" ]] || die "Backup directory not found: $BACKUP_DIR"

DUMP_FILE="$(find_single_file "$BACKUP_DIR" '*.dump' 'database dump')"
MODULES_FILE="$BACKUP_DIR/modules.txt"
[[ -f "$MODULES_FILE" ]] || die "Missing modules.txt in $BACKUP_DIR"
FILESTORE_ARCHIVE="$(find_optional_file "$BACKUP_DIR" 'filestore_*.tar.gz' 'filestore archive')"

declare -a EXPECTED_MODULES=()
while IFS= read -r line || [[ -n "$line" ]]; do
  line="$(trim "$line")"
  if [[ -n "$line" ]]; then
    EXPECTED_MODULES+=("$line")
  fi
done < "$MODULES_FILE"
[[ ${#EXPECTED_MODULES[@]} -gt 0 ]] || die "No modules found in $MODULES_FILE"

if [[ -z "$REPORT_FILE" ]]; then
  REPORT_FILE="$BACKUP_DIR/restore_drill_${TARGET_DB}.txt"
fi

COMPOSE_CMD=(docker compose)
if [[ -n "$COMPOSE_PROJECT_NAME" ]]; then
  COMPOSE_CMD+=(-p "$COMPOSE_PROJECT_NAME")
fi
COMPOSE_CMD+=(-f "$COMPOSE_FILE")

echo "Restore drill plan"
echo "  Backup dir:      $BACKUP_DIR"
echo "  Dump file:       $DUMP_FILE"
echo "  Modules file:    $MODULES_FILE"
echo "  Target DB:       $TARGET_DB"
echo "  Compose file:    $COMPOSE_FILE"
echo "  DB service:      $DB_SERVICE"
echo "  DB user:         $DB_USER"
echo "  Module count:    ${#EXPECTED_MODULES[@]}"
echo "  Report file:     $REPORT_FILE"
if [[ -n "$FILESTORE_ARCHIVE" && "$SKIP_FILESTORE" == false ]]; then
  echo "  Filestore:       $FILESTORE_ARCHIVE"
elif [[ "$SKIP_FILESTORE" == true ]]; then
  echo "  Filestore:       skipped by flag"
else
  echo "  Filestore:       no archive present"
fi

if [[ "$DRY_RUN" == true ]]; then
  exit 0
fi

if [[ "$AUTO_CONFIRM" == false ]]; then
  read -r -p "Drop and recreate '$TARGET_DB' for the restore drill? [y/N] " reply
  if [[ ! "$reply" =~ ^[Yy]$ ]]; then
    log "Restore drill cancelled."
    exit 1
  fi
fi

log "Ensuring database service is up"
"${COMPOSE_CMD[@]}" up -d "$DB_SERVICE" >/dev/null

log "Dropping and recreating restore target database '$TARGET_DB'"
"${COMPOSE_CMD[@]}" exec -T "$DB_SERVICE" psql -U "$DB_USER" -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$TARGET_DB' AND pid <> pg_backend_pid();" >/dev/null
"${COMPOSE_CMD[@]}" exec -T "$DB_SERVICE" dropdb --if-exists -U "$DB_USER" "$TARGET_DB"
"${COMPOSE_CMD[@]}" exec -T "$DB_SERVICE" createdb -U "$DB_USER" "$TARGET_DB"

log "Restoring database dump into '$TARGET_DB'"
"${COMPOSE_CMD[@]}" exec -T "$DB_SERVICE" pg_restore -U "$DB_USER" -d "$TARGET_DB" < "$DUMP_FILE"

if [[ -n "$FILESTORE_ARCHIVE" && "$SKIP_FILESTORE" == false ]]; then
  log "Restoring filestore into $FILESTORE_ROOT/$TARGET_DB"
  restore_filestore_archive "$FILESTORE_ARCHIVE" "$TARGET_DB"
else
  log "Skipping filestore restore"
fi

log "Verifying restored modules"
sql_list="$(sql_literal_list "${EXPECTED_MODULES[@]}")"
declare -a RESTORED_MODULES=()
mapfile -t RESTORED_MODULES < <(
  "${COMPOSE_CMD[@]}" exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$TARGET_DB" -Atc \
    "SELECT name FROM ir_module_module WHERE name IN ($sql_list) AND state IN ('installed', 'to upgrade') ORDER BY name;"
)

declare -a MISSING_MODULES=()
declare -A RESTORED_LOOKUP=()
module_name=""
for module_name in "${RESTORED_MODULES[@]}"; do
  RESTORED_LOOKUP["$module_name"]=1
done
for module_name in "${EXPECTED_MODULES[@]}"; do
  if [[ -z "${RESTORED_LOOKUP[$module_name]:-}" ]]; then
    MISSING_MODULES+=("$module_name")
  fi
done

if [[ ${#MISSING_MODULES[@]} -gt 0 ]]; then
  printf 'Missing restored modules:\n' >&2
  printf ' - %s\n' "${MISSING_MODULES[@]}" >&2
  exit 1
fi

mkdir -p "$(dirname "$REPORT_FILE")"
cat > "$REPORT_FILE" <<EOF
restore_drill_completed_at=$(date '+%F %T')
backup_dir=$BACKUP_DIR
dump_file=$DUMP_FILE
target_db=$TARGET_DB
module_count_expected=${#EXPECTED_MODULES[@]}
module_count_verified=${#RESTORED_MODULES[@]}
filestore_archive=${FILESTORE_ARCHIVE:-none}
filestore_restored=$([[ -n "$FILESTORE_ARCHIVE" && "$SKIP_FILESTORE" == false ]] && echo yes || echo no)
EOF

log "Restore drill completed successfully"
log "Verified ${#RESTORED_MODULES[@]} expected modules in '$TARGET_DB'"
if [[ -n "$FILESTORE_ARCHIVE" && "$SKIP_FILESTORE" == false ]]; then
  log "Filestore restored under $FILESTORE_ROOT/$TARGET_DB"
fi
log "Report written to $REPORT_FILE"