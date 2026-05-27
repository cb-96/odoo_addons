# Contributing

This repository expects small, test-backed changes with matching documentation updates.

## Prerequisites

- Python 3.10 or newer for local linting
- Docker with Compose v2 for the containerized Odoo test runner
- Git Bash, WSL, or another POSIX shell for the `ci/*.sh` scripts on Windows

## Local setup

```bash
cp ci/.env.example ci/.env
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Keep `ci/.env` local-only. Integration keys can be copied from `ci/integrations.env.example` or provided by your shell environment.

## Focused test commands

Run targeted suites for the main maintained flows:

```bash
bash ./ci/run_tests.sh --suite competition_core
bash ./ci/run_tests.sh --suite portal_public_ops
bash ./ci/run_tests.sh --suite finance_reporting
bash ./ci/run_tests.sh --suite rosters_readiness_guard
```

Run an individual module when you only need a narrow slice:

```bash
bash ./ci/run_tests.sh --module sports_federation_result_control
```

List the named suites from the runner itself:

```bash
bash ./ci/run_tests.sh --list-suites
```

## Pre-push checks

```bash
black --check sports_federation_base sports_federation_tournament sports_federation_standings sports_federation_venues sports_federation_portal sports_federation_public_site ci
flake8 sports_federation_base sports_federation_tournament sports_federation_standings sports_federation_venues sports_federation_portal sports_federation_public_site ci
bash -n ci/run_tests.sh
bash -n ci/apply_env_to_ir_config.sh
bash -n ci/restore_backup_drill.sh
python3 ci/check_doc_freshness.py
python3 ci/check_markdown_links.py
python3 ci/check_module_owners.py
python3 ci/check_openapi_contracts.py
python3 ci/check_release_train.py
python3 ci/check_explain_snapshots.py
python3 ci/check_ci_hygiene.py
python3 ci/check_module_dependency_drift.py
bash ci/prune_ci_logs.sh 30
```

## CI/CD Pipeline

### Named test suites

The CI runner groups modules into named suites for focused feedback. Use the
suite that covers the area you changed:

| Suite | Modules covered |
|---|---|
| `competition_core` | Base, tournament, scheduling, results, standings critical path |
| `portal_public_ops` | Portal ownership, public routes, compliance, standings, venue-facing flows |
| `finance_reporting` | Finance bridge and reporting coverage |
| `rosters_readiness_guard` | Participant readiness regression and discovery gate |
| `release_surfaces` | Broader portal/public, match-day, compliance, notification release verification |
| `people_rosters_rules` | People, rosters, rules, and officiating modules |
| `ops_and_notifications` | Discipline, governance, notifications, import_tools, demo modules |

```bash
# Run a named suite
bash ./ci/run_tests.sh --suite competition_core

# Run a single module (fastest for narrow changes)
bash ./ci/run_tests.sh --module sports_federation_standings

# Run everything (use before merging)
bash ./ci/run_tests.sh

# List suites
bash ./ci/run_tests.sh --list-suites
```

### Reading CI output

The runner prints a results block at the end:

```
════════════════════════════════
  RESULTS
════════════════════════════════
  Exit code:     0
  Tests run:     62
  Tests passed:  62
  Tests failed:  0
  Test errors:   0
════════════════════════════════
```

A non-zero exit code means failure. Find the cause:

```bash
# Show failing test names and tracebacks
docker logs <container> 2>&1 | grep -A 20 "FAIL\|ERROR\|Traceback"
```

The container name is printed by `docker compose ps` or appears in the runner
output as `sf_ci-ci-odoo-run-<hash>`.

### CI gate stages

1. **Module install** — all declared modules install without error.
2. **Test run** — `TransactionCase` and `HttpCase` tests execute.
3. **Query-count checks** — `assertQueryCount` assertions verify no N+1
   regressions were introduced.
4. **EXPLAIN snapshots** — `ci/check_explain_snapshots.py` compares query
   plans against stored baselines.
5. **Doc freshness checks** — `ci/check_doc_freshness.py`, `check_markdown_links.py`,
   `check_module_owners.py`, `check_openapi_contracts.py` verify documentation
   and contracts are up to date.

### Iterating on a failing test

```bash
# 1. Make your code change
# 2. Run only the affected module
bash ./ci/run_tests.sh --module sports_federation_<name>
# 3. If it passes, run the full suite before pushing
bash ./ci/run_tests.sh --suite <suite>
```

Keep the `--keep` flag to leave the Docker stack running between iterations
(avoids paying the container startup cost each run):

```bash
bash ./ci/run_tests.sh --module sports_federation_standings --keep
# ... fix code ...
bash ./ci/run_tests.sh --module sports_federation_standings --keep
```

### Pre-push checks

Before pushing, run the static checks locally to avoid a CI round-trip:

```bash
black --check sports_federation_base sports_federation_tournament \
      sports_federation_standings sports_federation_venues \
      sports_federation_portal sports_federation_public_site ci
flake8 sports_federation_base sports_federation_tournament \
       sports_federation_standings sports_federation_venues \
       sports_federation_portal sports_federation_public_site ci
bash -n ci/run_tests.sh
python3 ci/check_doc_freshness.py
python3 ci/check_markdown_links.py
python3 ci/check_module_owners.py
python3 ci/check_openapi_contracts.py
python3 ci/check_release_train.py
python3 ci/check_explain_snapshots.py
python3 ci/check_module_dependency_drift.py
```

## Documentation expectations

- Update the relevant module README for behavior or schema changes.
- Update the matching workflow under `_workflows/` when business behavior changes.
- Run the [Intuitiveness review checklist](INTUITIVENESS_REVIEW_CHECKLIST.md) for major UX, naming, entry-point, and state-label changes.
- Keep `TECHNICAL_NOTE.md`, `CONTEXT.md`, `INTEGRATIONS.md`, and `STATE_AND_OWNERSHIP_MATRIX.md` aligned when the change affects their scope.
- Update `MODULE_OWNERS.yaml` whenever a new addon is introduced or primary module ownership changes.
- Update `RELEASE_TRAIN.md` when a change starts a new release window or needs train-level migration coordination.
- Update `DATA_RETENTION_POLICY.md` when a change modifies cleanup scope or retention windows for logs, staged deliveries, or generated report files.
- Update the relevant record under `adr/` when a change revises portal trust boundaries, reporting SQL-view policy, or public route ownership.
