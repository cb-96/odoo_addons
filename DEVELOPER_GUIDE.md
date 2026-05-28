# Developer Guide

Last updated: 2026-05-18
Owner: Federation Platform Team

This guide takes you from a fresh clone to a running development environment,
explains the project's module architecture, and describes common workflows for
implementing features.

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Docker + Compose v2 | 24+ / 2.x | Required for all test and dev containers |
| Python | 3.10+ | Local linting and CI scripts only |
| Git | any | |
| POSIX shell | bash 4+ | Windows users: use Git Bash or WSL |

---

## 1. Initial Setup

```bash
# 1. Clone the repository and enter it
git clone <repo-url>
cd odoo

# 2. Copy example environment files
cp addons/ci/.env.example addons/ci/.env
# Fill in SMTP, integration keys as needed — ci/.env is gitignored

# 3. Install Python tooling for linting and pre-push checks
python -m pip install --upgrade pip
python -m pip install -r addons/requirements.txt
```

### Start the development stack

```bash
docker compose up -d
```

Odoo is available at `http://localhost:10019`. Default admin credentials are set
in `config/odoo.conf`.

### Install the custom modules

After the container is up, go to **Settings → Apps**, search for
"Sports Federation", and install **Sports Federation Base** first. The rest
can be installed in any order after that, because Odoo resolves the dependency
chain declared in each `__manifest__.py`.

You can also install from the command line:

```bash
docker compose exec odoo odoo-bin \
  -d <db-name> \
  -i sports_federation_base,sports_federation_tournament,sports_federation_competition_engine \
  --stop-after-init
```

---

## 2. Module Architecture

```
sports_federation_base          Master data: clubs, teams, seasons, registrations
sports_federation_tournament    Competitions, stages, groups, participants, matches
sports_federation_competition_engine  Schedule-generation wizards (round-robin, knockout)

sports_federation_people        Player master data and license management
sports_federation_rules         Rule sets, scoring, tie-breaks, eligibility
sports_federation_rosters       Season rosters, match sheets, audit trail
sports_federation_officiating   Referees, certifications, match assignments
sports_federation_result_control  Result approval pipeline (submitted → approved)
sports_federation_standings     Standing computation and publication
sports_federation_compliance    Document requirements and submission tracking
sports_federation_discipline    Incidents, disciplinary cases, sanctions, suspensions
sports_federation_governance    Override requests, decisions, audit notes
sports_federation_finance_bridge  Fee schedules, finance events, accounting export
sports_federation_venues        Venues and playing areas

sports_federation_portal        Club-representative portal, registration flows
sports_federation_public_site   Public tournament pages, API feeds, editorial
sports_federation_notifications Email notifications and activity creation
sports_federation_reporting     SQL-view-backed analytics reports
sports_federation_import_tools  CSV import wizards, partner integration governance

sports_federation_demo          Demo data pack (install in dev/staging only)
```

**Dependency tiers — never import upward:**

```
Tier 1 (core):   base → tournament → competition_engine
Tier 2 (domain): people, rules, rosters, officiating, result_control,
                 standings, compliance, discipline, governance, venues,
                 finance_bridge
Tier 3 (surface): portal, public_site, notifications
Tier 4 (cross-cutting): reporting, import_tools
Tier 5 (data): demo
```

Tier 1 modules may not import from tiers 2–5. Tier 2 modules may only import
from tier 1 and peer tier-2 modules they explicitly depend on. The
`competition_engine` module contains no persistent models — it only provides
wizards and services.

---

## 3. Running Tests

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full CI/CD section.

Quick commands:

```bash
# Run a named test suite (fastest feedback for the area you changed)
bash addons/ci/run_tests.sh --suite competition_core

# Run a single module
bash addons/ci/run_tests.sh --module sports_federation_standings

# Run participant readiness discovery guard
bash addons/ci/run_tests.sh --suite rosters_readiness_guard

# List all named suites
bash addons/ci/run_tests.sh --list-suites
```

---

## 4. Creating Your First Tournament (Dev Walkthrough)

This walkthrough verifies your environment is working end to end.

### Step 1: Create master data

1. **Settings → Sports Federation → Clubs** → Create a club (`code: DEMO`)
2. **Teams** → Create two teams linked to the club
3. **Seasons** → Create a season (name: `2026-2027`, dates: 2026-09-01 to 2027-06-30)

### Step 2: Create a tournament

1. **Competitions → Tournaments** → New
2. Set `name`, `season_id`, `date_start`, set `state` to `Open`
3. Save

### Step 3: Add participants

On the tournament form, go to **Participants** tab → Add the two teams, set
`state = confirmed`.

### Step 4: Generate a round-robin schedule

1. **Action → Generate Round-Robin Schedule** (or use the wizard button)
2. Accept defaults → confirm
3. Verify that matches appear in the **Matches** tab

### Step 5: Publish

1. Set `website_published = True` on the tournament
2. Visit `http://localhost:10019/tournaments` — the tournament appears in the
   public list

---

## 5. Module Boundary Rules

These rules are enforced in code review; violating them breaks the upgrade path.

1. **`federation.*` model prefix** — all custom models use this prefix.
2. **`security/ir.model.access.csv` is mandatory** — every new model needs a
   row. Missing rows cause `AccessError` for non-superuser operations.
3. **Manifests declare all data files** — any XML or CSV file that needs to be
   loaded must appear in `__manifest__.py` `data` list. Files missing from
   `data` are silently ignored.
4. **No raw SQL in model code** — use the ORM. The only exception is
   `_auto = False` models in `sports_federation_reporting` (SQL views for
   analytics).
5. **Tier isolation** — a module must not import from a module it does not
   declare in `depends`.
6. **No `sudo()` in controllers without a scope check** — portal controllers
   must call `_assert_portal_owns()` or equivalent before any write that could
   affect records belonging to another club.

---

## 6. Common Pitfalls

### Stale routing cache

**Symptom:** A new route returns 404 in the running dev container even though
the Python is correct.

**Fix:** Odoo caches the routing map per registry key. Restart the container or
call `ir.http` clear cache from a shell:

```bash
docker compose restart odoo
```

### Missing ACL row

**Symptom:** `odoo.exceptions.AccessError: You are not allowed to access...`
even for admin users (or CI fails immediately after install).

**Fix:** Add a row to `security/ir.model.access.csv` for the new model. The
row format is:

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_federation_mymodel_manager,federation.mymodel.manager,model_federation_mymodel,sports_federation_base.group_federation_manager,1,1,1,1
```

### Unregistered data file

**Symptom:** XML records or `ir.config_parameter` defaults are not loaded
after install/upgrade.

**Fix:** Ensure the file path appears in `__manifest__.py` under the `"data"`
key. Order matters — `security/` files must come before `views/` files.

### `store=True` column doesn't exist

**Symptom:** `psycopg2.errors.UndefinedColumn` on a computed field.

**Fix:** If `store=True` was added after the initial install, the DB column was
never created. Options:
- Remove `store=True` if the field doesn't need to be searched/sorted in SQL
- Run a module upgrade: `docker compose exec odoo odoo-bin -d <db> -u <module> --stop-after-init`

### Computed field not recalculated

**Symptom:** A stored computed field shows stale values.

**Fix:** Check that `@api.depends(...)` lists every field the computation reads,
including fields on related models (`"related_id.field_name"`).

---

## 7. Code Style

- **Black** formatting, line length 88 (`.flake8` config in `ci/`)
- **flake8** for style checks
- Docstrings on all public methods (one-line or multi-line; first line is a
  short imperative sentence)
- Model method order: `_name/_description` → field declarations → `_CONSTRAINTS`
  → `@api.depends` computed fields → `@api.constrains` validators → `@api.onchange`
  → action methods → helper methods

Run pre-push checks:

```bash
black --check addons/sports_federation_base addons/sports_federation_tournament
flake8 addons/sports_federation_base addons/sports_federation_tournament
python3 addons/ci/check_doc_freshness.py
```

---

## 8. Documentation Expectations

Every PR that touches a model, route, workflow, or business rule must update
the relevant documentation in the same commit:

| Change type | Update target |
|---|---|
| New / changed model | Module `README.md`, `security/ir.model.access.csv` |
| New / changed route | `ROUTE_INVENTORY.md` |
| New / changed workflow | `_workflows/WORKFLOW_*.md` |
| New / changed state | `STATE_AND_OWNERSHIP_MATRIX.md` |
| New module | `MODULE_OWNERS.yaml`, `CONTEXT.md` |
| New data file | `__manifest__.py` `data` list |
| Breaking change | `COMPATIBILITY_INVENTORY.md`, `RELEASE_RUNBOOK.md` |

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full documentation checklist.
