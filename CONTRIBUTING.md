# Contributing

Changes are small, test-backed and ship with their documentation. This page
covers local setup, running tests, the checks to run before pushing, and the
checklists for a change. Background reading: the
[architecture overview](docs/architecture/overview.md) and the
[technical reference](docs/architecture/technical-reference.md).

## Prerequisites

- Python 3.10 or newer for local linting and contract checks
- Docker with the Compose plugin for the containerized Odoo test runner
- Git Bash, WSL or another POSIX shell for the `ci/*.sh` scripts on Windows
- Optional: Node.js for JavaScript syntax checks and browser helpers

## Local setup

```bash
cp ci/.env.example ci/.env
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Keep `ci/.env` local; never commit credentials. Integration keys can be copied
from `ci/integrations.env.example` or provided by the shell environment.

`requirements.txt` pins repository tooling only. The Odoo runtime comes from
the `odoo:19` image in `ci/docker-compose.ci.yaml`. If you also use a separate
local Odoo checkout, point its `addons_path` at this repository.

## Running tests

```bash
# One module (fastest while iterating)
bash ./ci/run_tests.sh --module sports_federation_result_control

# A named suite
bash ./ci/run_tests.sh --suite competition_core

# Changed addons and everything that depends on them
bash ./ci/run_tests.sh --affected-from origin/main --include-dependents

# Frontend-only checks for a module
bash ./ci/run_tests.sh --frontend-module sports_federation_portal

# List suites
bash ./ci/run_tests.sh --list-suites
```

Use `--keep` to leave the Docker stack running between iterations and
`--keep-on-failure` to keep the containers, database and logs only when a run
fails. Suites, logs and troubleshooting are described in
[CI and quality gates](docs/development/ci.md); test patterns, fixtures, tags
and query budgets in the [testing guide](docs/development/testing.md).

## Before pushing

```bash
bash ci/run_repo_lint.sh --strict
python3 ci/check_addon_integrity.py
python3 ci/check_model_load_order.py
python3 ci/check_portal_record_rules.py
python3 ci/check_migration_versions.py
python3 ci/check_module_dependency_drift.py
python3 ci/check_access_csv_integrity.py
python3 ci/check_translations.py
python3 ci/check_workflow_state_contracts.py
python3 ci/check_migration_review.py --base-ref origin/main
python3 ci/check_constraint_index_contracts.py
python3 ci/check_explain_snapshots.py
python3 ci/check_portal_sudo_guard.py
python3 ci/check_privileged_mutation_boundaries.py
python3 ci/check_doc_freshness.py
python3 ci/check_markdown_links.py
python3 ci/check_delivery_language.py
python3 ci/check_module_owners.py
python3 ci/check_openapi_contracts.py
python3 ci/check_release_train.py
python3 ci/check_competition_ui_workflow.py
```

`scripts/ci/run_rc_validation.sh static` runs the complete static lane used
for release candidates.

## Change checklist

For every behavioural change:

- [ ] Behaviour lives in the addon that owns the record; protected transitions
      go through one model command.
- [ ] New models have ACLs in `security/ir.model.access.csv` and record rules;
      company and portal scope are checked.
- [ ] New view, data and asset files are declared in `__manifest__.py`; direct
      dependencies are declared; `version` is bumped when an upgrade is needed.
- [ ] Packages export their files in `__init__.py`.
- [ ] User-facing text is translatable and the templates are re-exported
      (see [Translations](docs/development/translations.md)).
- [ ] A focused test covers the business rule (deterministic for scheduling
      and standings logic) and is tagged for suite selection.
- [ ] Documentation is updated in the same change (see below).

A new addon uses the standard layout (`models/`, `security/`, `views/`, and as
needed `data/`, `wizards/`, `controllers/`, `services/`, `tests/`), has a
`README.md`, an entry in `MODULE_OWNERS.yaml` and a row in the
[module catalogue](docs/overview/modules.md). Do not create empty
directories.

## Documentation

Every subject has one home; the [documentation map](docs/README.md#where-new-information-belongs)
says where each kind of change is documented. In short:

- addon behaviour, models and configuration → the addon `README.md`;
- states, transitions and business rules → the matching
  [workflow](docs/workflows/README.md) and, for core records,
  [state and ownership](docs/architecture/state-and-ownership.md);
- routes → the [route inventory](docs/reference/routes.md) and
  `ci/contracts/route_inventory.json`;
- menus → [backend navigation](docs/user-guide/backend-navigation.md);
- cross-cutting decisions → a [decision record](docs/architecture/decisions/README.md);
- retention windows → [data retention](docs/reference/data-retention.md);
- upgrade-sensitive changes → a new entry in the
  [upgrade notes](docs/operations/upgrade-notes.md).

Document the current system, not the delivery: no patch notes, "implemented
in this change" sections, validation logs or numbered delivery phases in the
documentation.

## Migration review

Changes to `models/`, `views/` or `controllers/` are upgrade-sensitive.
`ci/check_migration_review.py` requires, for each affected addon, a migration
script, a README update, a technical-reference update or route-ownership
documentation, and in every case an entry in the
[upgrade notes](docs/operations/upgrade-notes.md) with the dry run and the
rollback path. Before merging, confirm:

- schema, backfill, index, view, route and ACL implications are understood;
- `python3 ci/check_migration_review.py --base-ref origin/main` passes;
- the upgrade-notes entry records the dry-run command, its result, rollback
  triggers, backup requirements and any SQL reversal;
- the affected module tests and the relevant suite pass.

## Commits

Prefer one logical change per commit with a descriptive message
(`feat(scope): …`, `fix(scope): …`, `docs: …`).
