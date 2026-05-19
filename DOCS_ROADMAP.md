# Documentation Roadmap

Last updated: 2026-05-18
Owner: Federation Platform Team
Review cadence: Every release train

---

## Current State

The project has strong **foundational documentation**: 21 top-level governance
files, 19 of 20 module READMEs, 12 authoritative workflow docs, 3 ADRs, and
2 OpenAPI specs. The main gaps are in three areas that compound each other:
**no developer onboarding path**, **no operator deployment or troubleshooting
guides**, and **missing user-facing guides** for club representatives, referees,
and federation staff.

### Inventory at a glance

| Layer | Files | Status |
|---|---|---|
| Top-level governance docs | 21 | ✓ Complete |
| Workflow docs (`_workflows/`) | 12 | ~ 5 known gaps |
| Architecture decision records (`adr/`) | 3 | ~ Active decisions captured |
| OpenAPI specs (`openapi/`) | 2 | ~ Partner + public feeds only |
| Module READMEs | 19 / 20 | ~ Demo module missing |
| Developer guides | 0 dedicated files | ✗ Missing |
| Operator / deployment guides | 3 (runbook, retention, restore) | ✗ Missing deployment + troubleshoot |
| User-facing guides | 0 | ✗ Missing |

---

## Wave 1 — Developer Onboarding  *(target: next release)*

The highest-leverage gap. Nothing currently walks a new contributor from clone
to a running test suite or explains the module boundary rules beyond a
paragraph in README.md.

### D-01 · Developer Getting-Started Guide

**File:** `DEVELOPER_GUIDE.md`

Cover: prerequisites → clone → `ci/.env` setup → running `ci/run_tests.sh` →
creating a tournament in the dev database → module boundary rules
(`base → tournament → engine → domain modules`) → common pitfalls (stale
routing cache, missing ACL row, unregistered data file).

### D-02 · Testing Patterns Reference

**File:** `TESTING_GUIDE.md`

Cover: test class taxonomy (`TransactionCase` vs HTTP smoke tests) → portal
ownership fixture pattern (reference `skills/portal-access-fixtures/`) →
service-level regression test pattern (reference
`skills/service-regression-test-builder/`) → `assertQueryCount` budgets and
where they live → how to add an explain snapshot.

### D-03 · New Module Scaffold Guide

**File:** `MODULE_SCAFFOLD_GUIDE.md`

Cover: canonical directory layout → required wiring (manifest `data` list,
`security/ir.model.access.csv`, `models/__init__.py`, test file) →
`module-change-scaffold` skill reference → `copilot-instructions.md` PR
checklist. Include a worked example scaffolding a fictional
`sports_federation_awards` module.

### D-04 · CI/CD Pipeline Guide

**Section in `CONTRIBUTING.md`** (extend, do not create new file)

Cover: `ci/run_tests.sh` suite names and when to use each → how to interpret
container log output → how CI gates are structured → how to run a single test
class locally.

---

## Wave 2 — Workflow Gaps  *(target: +1 release)*

Five business processes either have no workflow doc or are only partially
treated inside longer workflow files.

### W-01 · Player License Lifecycle

**File:** `_workflows/WORKFLOW_PLAYER_LICENSE.md`

Cover: license creation (federation staff) → season activation → expiry
rules → suspension-check integration with `sports_federation_officiating` →
reinstatement path.

### W-02 · Club Onboarding

**File:** `_workflows/WORKFLOW_CLUB_ONBOARDING.md`

Cover: new club request → federation staff review → initial compliance
document intake (using `sports_federation_compliance`) → bank details entry
for finance bridge → first team/season registration → club representative
portal access grant.

### W-03 · Standing Recomputation & Freeze

**File:** `_workflows/WORKFLOW_STANDINGS_LIFECYCLE.md`

Cover: automatic recompute triggers (match result approved) → manual recompute
action → freeze-point decision (who can freeze, when) → publication approval
step before `website_published = True` → contested result impact on standings.

### W-04 · Club Representative Appeal

**File:** `_workflows/WORKFLOW_APPEAL_DISPUTE.md`

Cover: club rep raises dispute via `federation.override_request` → federation
staff governance review → decision recording → outcome applied (result
correction, sanction reduction, etc.) → notification to all parties.

### W-05 · Referee Availability & Self-Service

**Section added to `_workflows/WORKFLOW_OFFICIATING.md`**

Cover: referee marks availability windows → assignment engine skips
conflicting slots → referee accepts/declines via portal → confirmation
deadline and overdue escalation path.

---

## Wave 3 — Operational Guides  *(target: +2 releases)*

### O-01 · First-Time Deployment Guide

**File:** `DEPLOYMENT_GUIDE.md`

Cover: Docker Compose stack overview → `config/odoo.conf` settings →
environment variables (`SMTP_*`, `S3_*`, `INTEGRATION_*`) → initial database
creation → installing modules in order → first admin setup checklist →
post-install smoke test (open `/tournaments`, check notification dispatch).

### O-02 · Upgrade Path Documentation

**Section in `RELEASE_RUNBOOK.md`** per release train

Each release train adds a section covering: DB migrations (if any) →
`ir.config_parameter` additions → deprecated field removals → module install
order changes. Reference `COMPATIBILITY_INVENTORY.md` for route retirement
dates.

### O-03 · Troubleshooting Guide

**File:** `TROUBLESHOOTING.md`

Known issues and recovery steps to document:

| Symptom | Cause | Fix |
|---|---|---|
| Match form crashes with `UndefinedColumn` | Stored computed field added after install | Remove `store=True` or run upgrade |
| Standings not recomputing after result approval | `@api.depends` missing new field | Check depends chain; trigger manual recompute |
| Notifications not sending | SMTP misconfigured or dispatcher not installed | Check `ir.mail_server`; verify `sports_federation_notifications` is installed |
| Import wizard dry-run always fails | Duplicate key in staging table | Run `_gc_staged_deliveries` scheduled action or truncate staging table |
| Rate limit buckets never cleared | Scheduled action `_gc_rate_limit_buckets` disabled | Re-enable the GC scheduled action in Settings → Technical |
| CI container fails to start Postgres | Port conflict with running dev stack | Stop dev stack first or use different CI network |

### O-04 · Performance Tuning Reference

**Section in `PERFORMANCE_BASELINES.md`**

Cover: recommended PostgreSQL indexes beyond Odoo defaults → caching
strategies for public feed routes → how to interpret `assertQueryCount`
failures → adding EXPLAIN snapshots to `ci/explain_snapshots/`.

---

## Wave 4 — API & Integration Completeness  *(target: +3 releases)*

### A-01 · Portal API OpenAPI Spec

**File:** `openapi/portal_v1.yaml`

Formalise portal routes currently undocumented:
- `POST /my/tournament/<id>/register` — team registration submission
- `POST /my/match/<id>/sheet` — match sheet submission
- `GET /my/dashboard` — portal dashboard data
- `POST /my/match/<id>/result` — result submission

Apply same OpenAPI 3.1.0 structure and auth scheme as `integration_v1.yaml`.

### A-02 · Rate Limiting & Error Code Reference

**File:** `openapi/ERROR_CODES.md`

Cover: all `error_code` values returned by JSON endpoints (`retryable_delivery`,
`not_found`, `validation_error`, `unauthorized`, etc.) → per-scope rate limits
(from `federation.request.rate.limit._POLICIES`) → backoff recommendation →
`Retry-After` header semantics.

### A-03 · Integration Consumer Examples

**Directory:** `openapi/examples/`

Provide three canonical consumer examples:
- `fetch_tournaments.py` — Python script consuming `/competitions/api/json`
- `subscribe_feed.sh` — cURL polling `/api/v1/tournaments/<slug>/feed`
- `ingest_finance.py` — Python script pushing to the managed integration API

---

## Wave 5 — User-Facing Guides  *(target: post-next release, external docs site)*

These are lower priority for in-repo documentation; consider hosting on an
external docs site or Odoo website page once the system is in production use.

### U-01 · Federation Staff User Guide

Topics: create a competition → publish a tournament → assign referees in bulk
→ verify a match result → freeze standings → manage compliance submissions →
open a disciplinary case.

### U-02 · Club Representative Portal Guide

Topics: register a team for a season → register a team for a tournament →
manage a roster → submit a match sheet → view your team's results and standings
→ raise a dispute.

### U-03 · Referee Self-Service Guide

Topics: view upcoming assignments → accept or decline → check certification
status → mark availability.

### U-04 · Finance Operator Guide

Topics: view the finance event feed → reconcile against fee schedules →
export for accounting → configure a budget entry for a season.

---

## Architecture Diagrams  *(ongoing, low urgency)*

No diagrams currently exist; these would live in a `docs/diagrams/` directory
if the project adopts a diagrams-as-code tool (e.g. Mermaid, PlantUML).

| Diagram | Value |
|---|---|
| Module dependency graph | Prevents circular dependency introductions; useful for onboarding |
| Core ERD (base + tournament + engine) | Answers "how do club/team/season/match relate?" for new developers |
| Tournament state machine | Supplements `WORKFLOW_TOURNAMENT_LIFECYCLE.md` |
| Result pipeline sequence diagram | Supplements `WORKFLOW_RESULT_PIPELINE.md` |
| Portal trust boundary diagram | Supplements ADR-0001 |

---

## Maintenance Rules

1. **Doc changes travel with code changes.** Any PR that changes a model,
   workflow, state, or route must update the relevant README,
   `_workflows/*.md`, and/or top-level docs in the same commit. See
   `copilot-instructions.md` Documentation Maintenance section.

2. **Workflow docs are authoritative.** If code and a workflow doc disagree,
   the workflow doc defines the intended behaviour and the code is wrong.

3. **ADRs are append-only.** Superseded decisions get a new ADR; the old one
   is updated to "Superseded by ADR-NNNN".

4. **OpenAPI specs are versioned.** Breaking changes require a new `v2` path
   prefix and a compatibility window per `INTEGRATION_CONTRACTS.md`.

5. **Review this roadmap every release train.** Completed items move to an
   archive section; new gaps identified in the release review are added.
