# ROADMAP — Next Operating Period

Last updated: 2026-04-13

The multi-year build roadmap is complete and archived in `ROADMAP_archive_2026-04-13.md`.
This roadmap covers the next delivery period and shifts the repository from
feature expansion to workflow polish, stale-code retirement, and release
readiness.

## Period Goal

Move the platform from feature-complete and internally verified to
operator-friendly, browser-safe, and production-ready.

## Operating Principles

- Prefer workflow simplification over feature breadth.
- Remove or retire shadowed implementations instead of maintaining duplicates.
- Treat browser journeys as first-class acceptance criteria.
- Keep controller security, tests, documentation, and migration notes coupled to every workflow change.
- Make release and rollback procedures reproducible before calling a feature done.

## Current Baseline

- Years 1 through 4 of the original product roadmap are complete.
- Core federation workflows, portal surfaces, public tournament coverage, compliance self-service, reporting, finance automation, and partner contracts exist in code.
- The next bottleneck is not feature breadth; it is UX consistency, stale-code cleanup, and operational confidence.

## Workstreams

### Priority 0 — Browser Workflow Hardening

1. Done (2026-04-13): Repair browser journeys that currently fail with raw technical pages.
Modules: `sports_federation_compliance`, `sports_federation_portal`, `sports_federation_public_site`.
Work landed: compliance workspace detail links now resolve correctly for dotted target models, the login flow recovers from stale CSRF submissions with a guided retry message, and wrong-role tournament registration attempts now render readable feedback instead of raw ACL failures. The batch was verified with targeted live browser checks and focused CI.
Done when: closed in this execution batch.

2. Done (2026-04-13): Improve action clarity and empty states on self-service pages.
Modules: `sports_federation_portal`, `sports_federation_compliance`, `sports_federation_officiating`, `sports_federation_public_site`.
Work landed: self-service registration, compliance, officiating, and public tournament pages now explain the next action more clearly, surface readable status feedback, and replace the most visible dead-end empty states with guided messages. The expanded browser smoke suite exercises the primary happy-path and unhappy-path flows.
Done when: closed in this execution batch.

3. Done (2026-04-13): Replace leftover website boilerplate with federation-specific copy.
Modules: `sports_federation_public_site`, `sports_federation_portal`, website configuration.
Work landed: public tournament and season pages now use tournament-hub language instead of leftover generic coverage boilerplate, legacy public templates were retired or aligned, the website cleanup hook now removes stock shell menus and footer/company placeholders on install and upgrade, and the broader `release_surfaces` suite keeps the public and portal smoke flows in nightly/manual coverage.
Done when: closed in this execution batch.

### Priority 1 — Stale-Code Retirement and Route Simplification

1. Done (2026-04-13): Remove or quarantine superseded public tournament pages in the portal module.
Modules: `sports_federation_portal`, `sports_federation_public_site`.
Work landed: duplicate portal-owned public tournament controllers and their stale website templates were removed from active loading, leaving `sports_federation_public_site` as the canonical owner of the public tournament surface.
Done when: closed in this execution batch.

2. Done (2026-04-13): Finish or remove stubbed workflow branches.
Modules: `sports_federation_notifications`, `sports_federation_discipline`, `sports_federation_compliance`.
Work landed: suspension activation now drives a real direct-email notification path with outcome logging instead of emitting a false-positive stub success entry.
Done when: closed in this execution batch.

3. Done (2026-04-13): Review compatibility layers and legacy inputs with owners and exit dates.
Modules: `sports_federation_public_site`, `sports_federation_import_tools`, integration surfaces.
Work landed: added `COMPATIBILITY_INVENTORY.md` to document retained legacy routes, aliases, and inbound data shapes with owners, review checkpoints, and explicit exit timing.
Done when: closed in this execution batch.

### Priority 1 — Code Quality and Maintainability

1. Done (2026-04-13): Centralize privileged writes inside model or service entry points.
Modules: `sports_federation_portal`, `sports_federation_public_site`, `sports_federation_compliance`, `sports_federation_import_tools`.
Work landed: team creation, season registration, tournament registration, and compliance submissions now route through model-owned portal helpers that preserve request-user ownership while keeping elevated writes explicit and testable. Backend tests and `HttpCase` smoke coverage were added for those service boundaries.
Done when: closed in this execution batch.

2. Done (2026-04-13): Keep repository-wide developer documentation current.
Modules: repository-wide.
Work landed: added `ROUTE_INVENTORY.md`, refreshed `INTEGRATION_CONTRACTS.md`, updated the root README and affected module READMEs, and documented the release path in `RELEASE_RUNBOOK.md`.
Done when: closed in this execution batch.

3. Done (2026-04-13): Normalize naming and file-layout conventions.
Modules: repository-wide.
Work landed: normalized the import-tools package layout from `wizard/` to `wizards/` and aligned affected imports/documentation so the module structure is predictable across the suite.
Done when: closed in this execution batch.

### Priority 2 — Release Operations and Observability

1. Done (2026-04-13): Build a repeatable browser-first verification suite.
Modules: `ci`, `sports_federation_portal`, `sports_federation_public_site`, `sports_federation_compliance`, `sports_federation_reporting`.
Work landed: expanded Odoo `HttpCase` smoke coverage for stale login recovery, team creation, season registration, compliance detail routing, officiating responses, representative public registration, wrong-role feedback, and full-tournament unhappy paths; kept them in the broader `release_surfaces` suite for nightly/manual execution.
Done when: closed in this execution batch.

2. Done (2026-04-13): Prepare production rollout runbooks.
Modules: repository-wide.
Work landed: added `RELEASE_RUNBOOK.md` covering pre-release verification, dry runs, backups, upgrades, rollback, and post-upgrade operator checks for the Dockerized Odoo stack.
Done when: closed in this execution batch.

3. Done (2026-04-13): Strengthen operational observability.
Modules: `sports_federation_reporting`, `sports_federation_notifications`, `sports_federation_import_tools`, `sports_federation_finance_bridge`.
Work landed: added the reporting operator checklist surface, linked report schedules to persisted failure state, folded scheduled-report failures into the checklist/audit pack, and covered inbound delivery/reporting visibility with focused tests.
Done when: closed in this execution batch.

## Suggested Sequence

1. Browser error-state fixes and compliance/tournament workflow polish.
2. Duplicate route retirement planning and notification stub cleanup.
3. Controller/service cleanup plus naming and structure normalization.
4. Browser smoke-suite expansion and rollout runbook preparation.
5. Observability improvements and final production-readiness review.

## Exit Criteria For This Period

- No raw 400, 403, or 404 technical pages remain in primary user workflows.
- No shadowed public-route implementation remains without an explicit compatibility plan.
- No notification path reports `sent` unless something was actually delivered or intentionally queued.
- Browser flows and privileged writes have regression coverage.
- Release, rollback, and smoke verification are documented and reproducible.