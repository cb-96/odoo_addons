#!/usr/bin/env bash

set -uo pipefail

usage() {
    echo "Usage: bash ci/run_repo_lint.sh [--strict|--report]"
}

mode="strict"
if [[ $# -gt 1 ]]; then
    usage
    exit 2
fi
if [[ $# -eq 1 ]]; then
    case "$1" in
        --strict)
            mode="strict"
            ;;
        --report)
            mode="report"
            ;;
        *)
            usage
            exit 2
            ;;
    esac
fi

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir" || exit 1

if ! command -v black >/dev/null 2>&1; then
    echo "black is required but was not found on PATH."
    exit 2
fi
if ! command -v flake8 >/dev/null 2>&1; then
    echo "flake8 is required but was not found on PATH."
    exit 2
fi

black_exit=0
flake8_exit=0
ci_hygiene_exit=0
dependency_drift_exit=0
workflow_contracts_exit=0
migration_review_exit=0
constraint_index_contracts_exit=0
openapi_contracts_exit=0
http_route_ownership_exit=0
release_qualification_exit=0

echo "[lint] Running Black across the repository"
black --check --exclude '/(\.git|__pycache__|\.venv|ci/logs)/' . || black_exit=$?

echo "[lint] Running Flake8 across the repository"
flake8 . || flake8_exit=$?

echo "[lint] Running CI hygiene checks"
python3 ci/check_ci_hygiene.py || ci_hygiene_exit=$?

echo "[lint] Validating workflow state contracts"
python3 ci/check_workflow_state_contracts.py || workflow_contracts_exit=$?

echo "[lint] Validating constraint/index contracts"
python3 ci/check_constraint_index_contracts.py || constraint_index_contracts_exit=$?

echo "[lint] Validating OpenAPI integration/public contracts"
python3 ci/check_openapi_contracts.py || openapi_contracts_exit=$?

echo "[lint] Validating HTTP route ownership"
python3 ci/check_http_route_ownership.py || http_route_ownership_exit=$?

echo "[lint] Validating release qualification"
python3 ci/check_release_qualification.py || release_qualification_exit=$?

echo "[lint] Reporting module dependency drift"
python3 ci/check_module_dependency_drift.py || dependency_drift_exit=$?

echo "[lint] Checking migration review evidence"
lint_base_ref="${MIGRATION_REVIEW_BASE_REF:-origin/main}"
branch_changed_files=()
if git rev-parse --verify "$lint_base_ref" >/dev/null 2>&1; then
    mapfile -t branch_changed_files < <(
        git diff --name-only "${lint_base_ref}...HEAD"
    )
fi
mapfile -t lint_changed_files < <(
    {
        printf '%s\n' "${branch_changed_files[@]}"
        git diff --name-only HEAD
        git ls-files --others --exclude-standard
    } | sort -u
)
if [[ ${#lint_changed_files[@]} -gt 0 ]]; then
    python3 ci/check_migration_review.py --files "${lint_changed_files[@]}" || migration_review_exit=$?
else
    python3 ci/check_migration_review.py || migration_review_exit=$?
fi

echo
echo "[lint] Summary"
echo "  Black exit code:  $black_exit"
echo "  Flake8 exit code: $flake8_exit"
echo "  CI hygiene exit code: $ci_hygiene_exit"
echo "  Workflow contract exit code: $workflow_contracts_exit"
echo "  Constraint/index contract exit code: $constraint_index_contracts_exit"
echo "  OpenAPI contract exit code: $openapi_contracts_exit"
echo "  HTTP route ownership exit code: $http_route_ownership_exit"
echo "  Release qualification exit code: $release_qualification_exit"
echo "  Migration review exit code: $migration_review_exit"
echo "  Dependency drift report exit code: $dependency_drift_exit"

if [[ "$mode" == "strict" && ( $black_exit -ne 0 || $flake8_exit -ne 0 || $ci_hygiene_exit -ne 0 || $workflow_contracts_exit -ne 0 || $constraint_index_contracts_exit -ne 0 || $openapi_contracts_exit -ne 0 || $http_route_ownership_exit -ne 0 || $release_qualification_exit -ne 0 || $migration_review_exit -ne 0 ) ]]; then
    exit 1
fi

if [[ $black_exit -ne 0 || $flake8_exit -ne 0 || $ci_hygiene_exit -ne 0 || $workflow_contracts_exit -ne 0 || $constraint_index_contracts_exit -ne 0 || $openapi_contracts_exit -ne 0 || $http_route_ownership_exit -ne 0 || $release_qualification_exit -ne 0 || $migration_review_exit -ne 0 ]]; then
    echo "[lint] Repository-wide report found issues."
else
    echo "[lint] Repository-wide report is clean."
fi

exit 0