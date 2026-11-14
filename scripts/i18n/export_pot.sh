#!/usr/bin/env bash
# Rebuild <module>/i18n/<module>.pot for every addon with Odoo's own exporter.
#
# Installs all addons in a throw-away database of the CI stack
# (ci/docker-compose.ci.yaml), exports one template per module, copies the
# templates into the repository and brings every language file in step
# (scripts/i18n/sync_po.py). Run it after changing user-facing text; Weblate
# picks the new templates up from the repository.
#
# Usage: scripts/i18n/export_pot.sh [module ...]
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

if [[ $# -gt 0 ]]; then
  modules=("$@")
else
  mapfile -t modules < <(
    find . -maxdepth 2 -name __manifest__.py -path './sports_federation_*' \
      | sed 's|^\./||; s|/__manifest__.py$||' \
      | grep -v -e '^sports_federation_demo$' | sort
  )
fi
module_list="$(IFS=,; echo "${modules[*]}")"

project="sf-i18n-$$"
out_dir="$(mktemp -d)"
config="$(mktemp)"
export CI_POSTGRES_USER="${CI_POSTGRES_USER:-odoo}"
export CI_POSTGRES_PASSWORD="${CI_POSTGRES_PASSWORD:-odoo}"
export CI_POSTGRES_DB="${CI_POSTGRES_DB:-postgres}"
export CI_ODOO_DB_HOST="${CI_ODOO_DB_HOST:-ci-db}"
export CI_ODOO_DB_PORT="${CI_ODOO_DB_PORT:-5432}"
export CI_ODOO_CONFIG_PATH="$config"
cat > "$config" <<CONF
[options]
db_host = $CI_ODOO_DB_HOST
db_port = $CI_ODOO_DB_PORT
db_user = $CI_POSTGRES_USER
db_password = $CI_POSTGRES_PASSWORD
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/mnt/extra-addons
data_dir = /var/lib/odoo
without_demo = True
log_level = warn
CONF
chmod 0644 "$config"
chmod 0777 "$out_dir"

compose=(docker compose -p "$project" -f ci/docker-compose.ci.yaml)
cleanup() { "${compose[@]}" down -v >/dev/null 2>&1 || true; rm -rf "$out_dir" "$config"; }
trap cleanup EXIT

"${compose[@]}" build ci-odoo
"${compose[@]}" up -d --wait ci-db

run() {
  "${compose[@]}" run --rm --no-deps \
    -v "$out_dir:/mnt/i18n-out" \
    -v "$repo_root/scripts/i18n:/mnt/i18n-scripts:ro" \
    -e SF_I18N_MODULES="$module_list" -e SF_I18N_OUT=/mnt/i18n-out \
    ci-odoo sh -lc 'exec runuser -u odoo -- odoo "$@"' -- "$@"
}

run -d i18n_export -i "$module_list" --stop-after-init --no-http
"${compose[@]}" run --rm --no-deps \
  -v "$out_dir:/mnt/i18n-out" \
  -v "$repo_root/scripts/i18n:/mnt/i18n-scripts:ro" \
  -e SF_I18N_MODULES="$module_list" -e SF_I18N_OUT=/mnt/i18n-out \
  ci-odoo sh -lc 'exec runuser -u odoo -- odoo shell -d i18n_export --no-http < /mnt/i18n-scripts/export_pot.py'

for module in "${modules[@]}"; do
  if [[ -f "$out_dir/$module.pot" ]]; then
    mkdir -p "$module/i18n"
    cp "$out_dir/$module.pot" "$module/i18n/$module.pot"
  fi
done
python3 scripts/i18n/sync_po.py
echo "Templates exported for ${#modules[@]} module(s). Review and commit the i18n/ changes."
