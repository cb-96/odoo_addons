#!/usr/bin/env bash
# Test-only credentials; never import production integration secrets.
set -euo pipefail
suite="${1:?suite required}"
[[ "$suite" =~ ^[a-z0-9_]+$ ]] || { echo 'Invalid suite'; exit 1; }
[[ "${GITHUB_RUN_ID:-}" =~ ^[0-9]+$ ]] || exit 1
[[ "${GITHUB_RUN_ATTEMPT:-}" =~ ^[0-9]+$ ]] || exit 1
umask 077
project="sf_ci_${GITHUB_RUN_ID}_${GITHUB_RUN_ATTEMPT}_${suite}"
password="$(openssl rand -hex 16)"
cat > ci/.env <<EOF
CI_PROJECT_NAME=$project
CI_POSTGRES_USER=odoo
CI_POSTGRES_PASSWORD=$password
CI_POSTGRES_DB=postgres
CI_ODOO_DB_NAME=odoo_ci_test
CI_ODOO_DB_HOST=ci-db
CI_ODOO_DB_PORT=5432
CI_LOG_RETENTION_RUNS=3
CI_SKIP_BROWSER_BOOTSTRAP=0
EOF
# Fail clearly rather than invent a replacement image build.
test -f ci/Dockerfile.odoo-ci || { echo 'Missing ci/Dockerfile.odoo-ci in checkout'; exit 1; }
