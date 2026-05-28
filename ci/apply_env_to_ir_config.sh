#!/usr/bin/env bash
set -euo pipefail

# Apply selected integration environment variables into Odoo's
# ir.config_parameter using the `odoo shell` inside the CI Odoo image.
#
# Usage:
#   bash ci/apply_env_to_ir_config.sh <project_name> <compose_file> <env_file> <odoo_conf>
#
PROJECT_NAME="${1:-sf_ci}"
COMPOSE_FILE="${2:-ci/docker-compose.ci.yaml}"
LOADED_ENV_FILE="${3:-ci/.env}"
GENERATED_CONF="${4:-ci/odoo-ci.generated.runtime.conf}"
CONTAINER_CONF="/etc/odoo/odoo.conf"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ -f "$LOADED_ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$LOADED_ENV_FILE"
  set +a
fi

echo "[CI] Applying integration envs to Odoo ir.config_parameter (if any)" >&2

docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" run --rm ci-odoo odoo shell -c "$CONTAINER_CONF" <<'PY'
import os

keys = [
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_USE_TLS", "EMAIL_FROM",
    "SENDGRID_API_KEY", "MAILGUN_API_KEY",
    "OAUTH_GOOGLE_CLIENT_ID", "OAUTH_GOOGLE_CLIENT_SECRET", "OAUTH_GOOGLE_REDIRECT_URI",
    "OAUTH_GITHUB_CLIENT_ID", "OAUTH_GITHUB_CLIENT_SECRET", "OAUTH_GITHUB_REDIRECT_URI",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
    "SLACK_WEBHOOK_URL",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "S3_BUCKET", "S3_REGION", "ALLOWED_HOSTS",
]

for k in keys:
    v = os.environ.get(k)
    if v:
        keyname = 'integration.' + k.lower()
        env['ir.config_parameter'].set_param(keyname, v)
        print('SET', keyname)
PY

echo "[CI] apply_env_to_ir_config.sh completed" >&2
