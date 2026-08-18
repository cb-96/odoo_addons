#!/usr/bin/env bash
set -euo pipefail

find_repo_root() {
  local dir
  dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  while [[ "$dir" != "/" ]]; do
    if [[ -f "$dir/ci/run_tests.sh" ]]; then
      printf '%s\n' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

normalize_path() {
  local path="$1"
  path="${path#./}"
  if [[ -n "${REPO_ROOT:-}" && "$path" == "$REPO_ROOT"/* ]]; then
    path="${path#"$REPO_ROOT"/}"
  fi
  printf '%s\n' "$path"
}

extract_module() {
  local path="$1"
  local rest="$path"
  local segment

  while [[ "$rest" == */* ]]; do
    segment="${rest%%/*}"
    if [[ "$segment" == sports_federation_* ]]; then
      printf '%s\n' "$segment"
      return 0
    fi
    rest="${rest#*/}"
  done

  if [[ "$rest" == sports_federation_* ]]; then
    printf '%s\n' "$rest"
    return 0
  fi

  return 1
}

add_unique() {
  local value="$1"
  local entry
  for entry in "$@"; do
    if [[ "$entry" == "$value" ]]; then
      return 0
    fi
  done
  return 1
}

REPO_ROOT="$(find_repo_root)"
if [[ -z "$REPO_ROOT" ]]; then
  echo "Could not find repo root containing ci/run_tests.sh" >&2
  exit 1
fi

declare -a files=()
if [[ $# -gt 0 ]]; then
  files=("$@")
elif ! [ -t 0 ]; then
  while IFS= read -r line; do
    [[ -n "$line" ]] && files+=("$line")
  done
elif git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  while IFS= read -r line; do
    [[ -n "$line" ]] && files+=("$line")
  done < <(git -C "$REPO_ROOT" diff --name-only HEAD --)
else
  echo "Provide changed files as arguments or via stdin." >&2
  exit 1
fi

if [[ ${#files[@]} -eq 0 ]]; then
  echo "No changed files found. Provide file paths or create a git diff first."
  exit 0
fi

declare -a modules=()
declare -a reasons=()
declare -A suite_map=(
  [competition_core]="sports_federation_base sports_federation_tournament sports_federation_competition_engine sports_federation_result_control sports_federation_standings"
  [portal_public_ops]="sports_federation_portal sports_federation_public_site sports_federation_standings sports_federation_venues"
  [finance_reporting]="sports_federation_finance_bridge sports_federation_reporting"
)

cross_cutting=false
doc_touch=false

for raw_path in "${files[@]}"; do
  path="$(normalize_path "$raw_path")"

  if module="$(extract_module "$path" 2>/dev/null)"; then
    if ! printf '%s\n' "${modules[@]}" | grep -qx "$module"; then
      modules+=("$module")
    fi
  fi

  case "$path" in
    ci/*|.github/workflows/*)
      cross_cutting=true
      reasons+=("CI or workflow infrastructure changed: $path")
      ;;
    CONTEXT.md|TECHNICAL_NOTE.md|INTEGRATION_CONTRACTS.md|STATE_AND_OWNERSHIP_MATRIX.md)
      cross_cutting=true
      doc_touch=true
      reasons+=("Top-level architecture or operations docs changed: $path")
      ;;
    _workflows/*|README.md|ROADMAP.md)
      doc_touch=true
      ;;
  esac
done

declare -a candidate_suites=()
for suite in "${!suite_map[@]}"; do
  include_suite=true
  for module in "${modules[@]}"; do
    if [[ " ${suite_map[$suite]} " != *" $module "* ]]; then
      include_suite=false
      break
    fi
  done
  if [[ "$include_suite" == true && ${#modules[@]} -gt 0 ]]; then
    candidate_suites+=("$suite")
  fi
done

full_ci=false
if [[ "$cross_cutting" == true ]]; then
  full_ci=true
elif [[ ${#candidate_suites[@]} -eq 0 && ${#modules[@]} -gt 1 ]]; then
  full_ci=true
  reasons+=("Changed addons do not fit inside one named suite.")
fi

printf 'Repository root: %s\n' "$REPO_ROOT"
printf 'Files analyzed: %s\n' "${#files[@]}"
printf '\n'

if [[ ${#modules[@]} -gt 0 ]]; then
  printf 'Modules:\n'
  printf '  %s\n' "${modules[@]}"
  printf '\nSuggested module CI:\n'
  for module in "${modules[@]}"; do
    printf '  bash ./ci/run_tests.sh --module %s\n' "$module"
  done
else
  printf 'Modules:\n'
  printf '  none inferred from file paths\n'
fi

printf '\n'
if [[ ${#candidate_suites[@]} -gt 0 ]]; then
  printf 'Suggested suite CI:\n'
  printf '  bash ./ci/run_tests.sh --suite %s\n' "${candidate_suites[@]}"
else
  printf 'Suggested suite CI:\n'
  printf '  no single named suite fully covers the changed addons\n'
fi

printf '\nFull CI recommended: %s\n' "$full_ci"
if [[ ${#reasons[@]} -gt 0 ]]; then
  printf 'Reasons:\n'
  printf '  %s\n' "${reasons[@]}"
elif [[ "$doc_touch" == true ]]; then
  printf 'Reasons:\n'
  printf '  Workflow or repo docs changed. Consider broader validation if behavior changed with the docs.\n'
fi