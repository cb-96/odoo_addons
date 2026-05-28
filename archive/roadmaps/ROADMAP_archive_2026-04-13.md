# ROADMAP — Multi-Year Product and Engineering Plan

Last updated: 2026-04-12

This roadmap replaces the short tactical plan with a multi-year view organized
around the module boundaries already present in the repository. The goal is to
move from a strong technical base to a release-ready federation platform, then
to a more automated, self-service, and analytics-driven operating model.

## Planning Principles

- Close end-to-end workflows before adding feature breadth.
- Keep module boundaries intact and push reusable logic into services and
  wizards rather than cross-module shortcuts.
- Treat tests, security, documentation, and migration notes as part of feature
  completion.
- Prioritize federation-critical flows first: registration, eligibility,
  scheduling, match-day execution, results, standings, finance, and publication.
- Keep mail, OAuth, and external integrations env-driven and reproducible in CI.

## Module Groups

Core competition platform:
`sports_federation_base`, `sports_federation_tournament`,
`sports_federation_competition_engine`, `sports_federation_result_control`,
`sports_federation_standings`

Participant and operations modules:
`sports_federation_people`, `sports_federation_rosters`,
`sports_federation_officiating`, `sports_federation_venues`,
`sports_federation_rules`

Oversight and control modules:
`sports_federation_discipline`, `sports_federation_governance`,
`sports_federation_compliance`

Delivery surfaces and supporting utilities:
`sports_federation_portal`, `sports_federation_public_site`,
`sports_federation_notifications`, `sports_federation_reporting`,
`sports_federation_import_tools`, `sports_federation_finance_bridge`

## Multi-Year Plan Overview

| Year | Theme | Primary Outcome | Main Module Focus |
| --- | --- | --- | --- |
| Year 1 | Release readiness and workflow closure | Stable, testable, secure federation core ready for pilot or first production rollout | Base, tournament, competition engine, people, rosters, result control, standings, portal, public site, venues, finance bridge, notifications, reporting |
| Year 2 | Operational depth and federation controls | Policy-heavy modules become first-class operational tools | Discipline, governance, compliance, finance bridge, officiating, reporting, notifications, import tools |
| Year 3 | Self-service and ecosystem expansion | Clubs and federation staff operate more through portal/public workflows and external integrations | Portal, public site, notifications, import tools, reporting, finance bridge |
| Year 4 | Intelligence, planning, and scale | Federation-wide analytics, stronger reconciliation, and outward-facing interfaces | Reporting, compliance, governance, finance bridge, base, import tools |

## Year 1 Goal

Year 1 is about making the suite dependable enough for real operational use.
That means finishing the core federation lifecycle, reducing manual workarounds,
hardening security, and ensuring every critical flow is supported by tests,
documentation, and operator-safe UI or wizard behavior.

## Year 1 Detailed Breakdown By Priority

### Priority 0 — Must-Have Foundation and Release Blockers

1. Done (2026-04-10): Stabilize canonical master data and state models.
Modules: `sports_federation_base`, `sports_federation_people`, `sports_federation_tournament`, `sports_federation_portal`.
Work: review all core records for mandatory fields, sequences, archive behavior, ownership fields, and state transitions; align technical notes, workflows, and tests with the actual ORM implementation.
Done when: core records used in season registration and competition operations have clear lifecycle coverage, explicit ACLs, and focused tests.

2. Done (2026-04-10): Close the season registration flow end to end.
Modules: `sports_federation_base`, `sports_federation_people`, `sports_federation_portal`, `sports_federation_finance_bridge`, `sports_federation_notifications`.
Work: move a club from draft registration through portal submission, validation, confirmation, finance-event creation, and notification logging without manual bridging steps.
Done when: one reproducible flow covers draft to confirmed registration with side effects that are idempotent and tested.

3. Done (2026-04-10): Make competition setup deterministic and operator-safe.
Modules: `sports_federation_tournament`, `sports_federation_competition_engine`, `sports_federation_rules`, `sports_federation_venues`.
Work: harden tournament templates, stage/group setup, round-robin generation, knockout bracket generation, gameday assignment, and stage progression; ensure preview-first behavior and overwrite safeguards in wizards.
Done when: administrators can generate schedules repeatedly with deterministic outputs and no destructive surprises.

4. Done (2026-04-10): Lock down result integrity and standings correctness.
Modules: `sports_federation_result_control`, `sports_federation_standings`, `sports_federation_rules`.
Work: enforce submit, verify, approve separation of duties; ensure contested and corrected results behave correctly; keep official standings limited to approved outcomes; preserve tie-break explanation visibility.
Done when: official standings can be defended operationally and every exception path has regression coverage.

5. Done (2026-04-10): Harden portal and public-site security before wider rollout.
Modules: `sports_federation_portal`, `sports_federation_public_site`.
Work: verify ownership checks on portal writes, validate all public visibility flags, avoid unsafe template rendering, and cover direct-URL access paths with controller tests.
Done when: public and portal surfaces enforce the same data-ownership and publication rules described in the workflows.

6. Done (2026-04-10): Standardize CI, secrets handling, and contributor setup. 
Modules: repository-wide, with emphasis on `ci/`, `sports_federation_public_site`, `sports_federation_portal`, `sports_federation_standings`, `sports_federation_venues`, `sports_federation_finance_bridge`, `sports_federation_reporting`.
Work: keep CI env-driven, expand targeted module tests, validate scripts, and document local execution for maintainers.
Done when: contributors can run focused tests locally and GitHub Actions can validate critical flows without committed secrets.

7. Done (2026-04-10): Bring repository documentation up to release quality.
Modules: repository docs plus every module touched by critical workflow work.
Work: keep `TECHNICAL_NOTE.md`, `CONTEXT.md`, workflow documents, module READMEs, integration docs, and state/ownership references aligned with the implemented code.
Done when: a new maintainer can understand the main system flows without relying on tribal knowledge.

### Priority 1 — High-Value Operational Completeness

1. Done (2026-04-10): Apply eligibility and license rules in real workflows.
Modules: `sports_federation_people`, `sports_federation_rules`, `sports_federation_rosters`, `sports_federation_portal`, `sports_federation_tournament`.
Work: connect eligibility checks to participant confirmation, roster validation, and match-sheet readiness; present operator-readable failure reasons instead of opaque blocks.
Done when: ineligible players are blocked consistently before official competition actions.

2. Done (2026-04-10): Complete roster and match-sheet operations.
Modules: `sports_federation_rosters`, `sports_federation_people`, `sports_federation_portal`, `sports_federation_result_control`.
Work: support season rosters, match-day roster locking, substitutions governance, and audit history tied to results and disputes.
Done when: match-day participation is traceable and synchronized with eligibility and discipline status.

3. Done (2026-04-10): Complete officiating assignment and confirmation workflows.
Modules: `sports_federation_officiating`, `sports_federation_tournament`, `sports_federation_venues`, `sports_federation_notifications`.
Work: add assignment statuses, confirmation deadlines, shortage alerts, and readiness checks for required official roles.
Done when: operationally ready matches can be identified automatically and missing-official cases create visible exceptions.

4. Done (2026-04-10): Expand finance automation from events to process support.
Modules: `sports_federation_finance_bridge`, `sports_federation_base`, `sports_federation_tournament`, `sports_federation_discipline`, `sports_federation_venues`, `sports_federation_reporting`.
Work: extend hooks for reimbursements, discipline-related charges, venue settlements, and reconciliation-friendly references.
Done when: most federation-triggered monetary events are created automatically, remain idempotent, and are exportable.

5. Done (2026-04-10): Activate the modeled notification scenarios.
Modules: `sports_federation_notifications`, `sports_federation_portal`, `sports_federation_public_site`, `sports_federation_result_control`, `sports_federation_standings`, `sports_federation_finance_bridge`.
Work: replace notification stubs with actual templates or activities for registration, publication, referee assignment, approved results, standings freeze, and finance confirmations.
Done when: high-value workflow events reliably produce a logged communication or task.

6. Done (2026-04-10): Expand reporting from CSV extraction to operational reporting.
Modules: `sports_federation_reporting`, `sports_federation_standings`, `sports_federation_finance_bridge`, `sports_federation_tournament`, `sports_federation_compliance`.
Work: provide federation-facing KPI outputs, reconciliation views, and role-oriented reports that do not require direct database access.
Done when: administrators can produce recurring weekly or monthly operational views from the application layer.

7. Done (2026-04-10): Make imports safe enough for onboarding and seasonal rollover.
Modules: `sports_federation_import_tools`, `sports_federation_base`, `sports_federation_people`, `sports_federation_tournament`.
Work: add dry-run validation, duplicate detection, failure reporting, and mapping guidance for initial club, team, player, and season data imports.
Done when: federation onboarding and annual data refreshes can be rehearsed with predictable outcomes.

### Priority 2 — Control, Oversight, and Policy Execution

1. Done (2026-04-12): Complete the discipline pipeline and connect it to operations.
Modules: `sports_federation_discipline`, `sports_federation_result_control`, `sports_federation_people`, `sports_federation_rosters`, `sports_federation_standings`.
Work: turn recorded incidents into sanctions, suspensions, and downstream eligibility effects that are visible in roster and match validation; keep sanction-side finance hooks and suspension-aware eligibility checks aligned with the operational date.
Done when: discipline outcomes automatically affect player availability and remain auditable.

2. Done (2026-04-12): Build compliance operations around real federation obligations.
Modules: `sports_federation_compliance`, `sports_federation_people`, `sports_federation_governance`, `sports_federation_portal`, `sports_federation_reporting`.
Work: track required documents, expiries, remediation tasks, and escalation states for clubs, officials, and staff.
Done when: overdue compliance items appear in actionable queues and reporting outputs.

3. Done (2026-04-12): Formalize governance and override controls.
Modules: `sports_federation_governance`, `sports_federation_standings`, `sports_federation_result_control`, `sports_federation_compliance`.
Work: capture approval trails for exceptional decisions, appeals, competition overrides, and federation directives.
Done when: extraordinary decisions are role-gated, auditable, and visible in reporting.

4. Done (2026-04-12): Add cross-module reconciliation and audit support.
Modules: `sports_federation_reporting`, `sports_federation_finance_bridge`, `sports_federation_notifications`, `sports_federation_governance`, `sports_federation_compliance`.
Work already landed: operational KPI reporting, standings reconciliation, finance follow-up reconciliation, failed-notification exception views, missing disciplinary-fine-event exception views, stalled workflow exception queues, approved-but-unimplemented override visibility, and season-level operator checklists.
Done when: federation operators can detect broken processes before end users report them.

### Priority 3 — Strategic Stretch Work If Capacity Remains

1. Done (2026-04-12): Deepen public tournament storytelling and discoverability.
Modules: `sports_federation_public_site`, `sports_federation_reporting`, `sports_federation_standings`, `sports_federation_tournament`.
Work already landed: tournament-first website navigation, slug-first public tournament and team routes, featured/live/archive hub sections, editorial summaries and pinned announcements, team profile pages, grouped schedule sections, bracket views, ICS calendar export, public JSON listing, versioned tournament feed payloads, publication guards, and automatic cleanup of stale legacy `/competitions` website menus during install and upgrade.
Done when: public pages reduce ad hoc communication load on federation staff.

2. Done (2026-04-12): Add federation-admin productivity tooling.
Modules: `sports_federation_portal`, `sports_federation_import_tools`, `sports_federation_notifications`, `sports_federation_reporting`.
Work already landed: portal club workflows, roster and match-sheet review pages, import dry-run wizards, recurring report schedules, season checklists, and queue-first review screens for workflow exceptions.
Done when: recurring seasonal administration takes fewer manual steps and fewer side-channel spreadsheets.

3. Done (2026-04-12): Prototype outward-facing integration contracts.
Modules: `sports_federation_reporting`, `sports_federation_finance_bridge`, `sports_federation_notifications`, `sports_federation_import_tools`.
Work already landed: authenticated CSV export endpoints for standings, participation, and finance summaries, repeatable import contracts for onboarding and seasonal rollover, and a stable versioned public tournament feed.
Done when: external integrations can be introduced without bypassing the module architecture.

## Year 1 Sequencing Guidance

Priority 0 through Priority 3 are now complete for the Year 1 scope.
Priority 2 closed with live workflow-exception queues and season checklist
reporting on top of the earlier standings, finance, notification-failure, and
missing-finance-event visibility. Priority 3 also closed: public tournament
surfaces now include a tournament-first website hub, slug-first public routes,
team profiles, grouped schedule and bracket presentation, ICS export, and a
stable versioned tournament feed alongside the existing CSV contracts.

Year 1 is therefore complete as a release-readiness phase. Remaining follow-up
work should be treated as Year 2+ optimization, scale, and operational depth,
not as missing baseline capability for pilot rollout.

Current Year 1 execution batch completed in this pass:

1. Done (2026-04-12): Wire active discipline suspensions into shared eligibility checks used by roster and match workflows.
2. Done (2026-04-12): Add operator-facing exception reports for failed notifications and missing disciplinary fine finance events.
3. Done (2026-04-12): Add workflow exception queues and season checklist reporting for federation operators.
4. Done (2026-04-12): Ship grouped public schedule, bracket, team profile, and calendar export pages for published tournaments.
5. Done (2026-04-12): Publish a stable v1 public tournament feed and slug-first public routes for external consumers.
6. Done (2026-04-12): Normalize stale legacy website competition menus automatically on install and upgrade.

## Current Baseline Entering Year 2

The repository is now beyond a generic “core federation MVP” baseline. The
implemented platform already includes a deeper operational foundation that
should be treated as Year 2 input, not as future aspiration.

Core competition and scheduling baseline already present:

- Tournament templates can scaffold repeatable event structures instead of relying on manual stage-by-stage setup.
- Stage progression rules, seeded advancement, persistent tournament rounds, and bracket-linked knockout flows are modeled explicitly in the ORM.
- Schedule generation is preview-first, deterministic, and guarded by overwrite warnings rather than destructive defaults.
- Result approval is separation-of-duties aware and feeds approved-only standings updates.

Eligibility, roster, and match-day baseline already present:

- A shared eligibility service evaluates season, club, license, and date-scoped suspension rules in one place.
- Team rosters are activation-gated, surface readable readiness feedback, and become structurally locked once live match-sheet activity references them.
- Match sheets support starter/substitute structure, substitution timing, approval, locking, and a participation audit trail.
- Tournament participants reuse team-linked roster readiness checks and enforce an operational roster deadline ahead of match-day workflows.

Officiating, finance, and oversight baseline already present:

- Referee assignments enforce 48-hour confirmation deadlines, certification-window validation, shortage visibility, and match-level officiating readiness aggregation.
- Finance events are auto-created and kept idempotent for season registration, approved-result charges, discipline fines, referee reimbursements, and venue bookings.
- Discipline, compliance, and governance modules already feed eligibility, workflow exceptions, and audit-facing reporting rather than acting as isolated back-office records.

Delivery surface and reporting baseline already present:

- The public site now runs as a tournament-first hub with slug-first routes, team profiles, grouped schedules, bracket pages, editorial controls, ICS export, and a stable versioned feed.
- Portal workflows already cover season and tournament registration review plus roster and match-sheet visibility with ownership controls.
- Reporting already includes operational KPI views, standings reconciliation, finance reconciliation, failed-notification exceptions, missing-finance exceptions, workflow exception queues, and season checklists.
- Import tooling already supports rehearsal-first onboarding and rollover imports for clubs, seasons, teams, players, and tournament participants.

## Year 2 Overview — Operational Depth and Federation Control

Year 2 should build on the implemented queues, reports, portal flows, and
public surfaces rather than treating discipline, compliance, governance,
reporting, and publication as net-new work. The next phase should focus on
hardening operational ownership, explicit external contracts, audit-friendly
reporting, and deeper self-service on top of the current baseline.

Target outcome: federation staff can run policy-heavy operations from explicit
queues and audit views inside the platform rather than through email,
spreadsheets, and ad hoc follow-up.

Year 2 completion status:

1. Done (2026-04-12): Run a coverage and regression audit on the highest-risk orchestration paths.
Work already landed: knockout auto-advance and bye wiring regression coverage, portal team-scope access regression coverage, finance handoff workflow tests, reporting regression expansion, and install/upgrade-safe website menu cleanup validation.

2. Done (2026-04-12): Add SLA-style queue ownership and escalation rules across workflow exceptions, compliance remediation, governance review, failed notifications, and finance follow-up.
Work already landed: SLA fields and queue ownership surfaces in the reporting layer for finance reconciliation, notification exceptions, workflow exceptions, and compliance remediation.

3. Done (2026-04-12): Turn the reporting layer into board and audit packs with historical trend views.
Work already landed: recurring board packs, audit packs, trend snapshots, compliance remediation queues, and season-readiness reporting.

4. Done (2026-04-12): Define the accounting-system handoff for `federation.finance.event`.
Work already landed: export, reconciliation, and closure workflow states; accounting-batch and reconciliation references; a detailed finance-event handoff CSV contract; and focused workflow tests.

5. Done (2026-04-12): Expand self-service roles in the portal toward coach and manager operations.
Work already landed: team-scoped coach and team-manager representative roles, scoped portal access, match-day preparation pages, match-sheet preparation helpers, and focused portal regression coverage.

6. Done (2026-04-12): Harden partner-facing integration contracts with documented versioning and deprecation policy.
Work already landed: explicit contract headers for authenticated CSV exports, public feed and ICS contract headers, documented versioning and deprecation policy in `INTEGRATION_CONTRACTS.md`, and canonical slug-first public routes retained alongside compatibility aliases.

7. Done (2026-04-12): Add import governance for high-impact seasonal rollover work.
Work already landed: reusable import templates, checksum-bound approval jobs, preview-first approval checkpoints, and post-import verification summaries with before/after record counts.

Year 2 is now complete as an operational-depth phase. The codebase has moved
from release-readiness into governed federation operations with explicit audit,
handoff, and partner-contract surfaces.

## Year 3 Overview — Self-Service and Ecosystem Expansion

Year 3 should deepen the self-service and integration layers that now exist in
baseline form. The portal should become the preferred interface for more club
operations, the public site should deepen tournament storytelling and fan-safe
publication workflows, and the existing export contracts should mature from
internal CSV and public-feed endpoints into stable partner-facing interfaces.

Target outcome: fewer manual interventions by federation staff and cleaner data
exchange with external systems and stakeholders.

## Year 3 Detailed Breakdown By Priority

### Priority 0 — Highest-Leverage Self-Service Workflows

1. Done (2026-04-12): Add referee self-service assignment response in the portal.
Modules: `sports_federation_portal`, `sports_federation_officiating`.
Work already landed: portal-linked referee profiles, official-only assignment access, upcoming-assignment pages, confirm and decline actions with response notes, backend linkage fields, and focused regression coverage.
Done when: assigned officials can review only their own matches and respond without federation staff manually relaying confirmations.

2. Done (2026-04-12): Expand club portal operations from registration into recurring tournament administration.
Modules: `sports_federation_portal`, `sports_federation_rosters`, `sports_federation_result_control`, `sports_federation_tournament`.
Work already landed: a unified active-tournament portal workspace with per-team entries, registration checkpoints, preferred-roster and roster-freeze visibility, match-day submission tracking, result follow-up summaries, direct links into roster and match-sheet pages, and focused regression coverage for club- and team-scoped users.
Done when: club staff can manage their recurring tournament obligations from one portal workspace instead of navigating multiple isolated pages.

3. Done (2026-04-12): Add self-service compliance submission and renewal workflows.
Modules: `sports_federation_portal`, `sports_federation_compliance`, `sports_federation_reporting`, `sports_federation_notifications`.
Work already landed: portal compliance workspace and detail pages, club- and referee-scoped requirement entries, attachment-backed portal submissions and renewals, renewal due-soon indicators, remediation-note visibility from reporting, notification hook reuse, and focused regression coverage.
Done when: federation staff no longer have to collect routine compliance renewals over email.

### Priority 1 — Public Experience and Publication Workflows

1. Done (2026-04-12): Deepen public tournament storytelling with editorial scheduling and season-wide discovery.
Modules: `sports_federation_public_site`, `sports_federation_reporting`, `sports_federation_notifications`.
Work already landed: public season slugs and landing pages, featured and recent tournament discovery by season, editorial items with draft and scheduled publication windows, season-, tournament-, and team-anchored highlights, pinned tournament announcements, and operator-safe publication controls.
Done when: federation staff can plan public communications inside the platform instead of publishing ad hoc updates manually.

2. Done (2026-04-12): Expose safer public follow experiences for teams, calendars, and results.
Modules: `sports_federation_public_site`, `sports_federation_portal`, `sports_federation_standings`.
Work already landed: slug-first team profile pages, grouped team schedule and result surfaces, season discovery links into published coverage, team schedule ICS export, stable team feed payloads, and publication-guarded follow helpers that preserve existing visibility controls.
Done when: recurring supporter and club communication needs are served by stable public pages and feeds.

### Priority 2 — Partner Integrations and Ecosystem Interfaces

1. Done (2026-04-12): Move from internal export contracts toward managed partner integrations.
Modules: `sports_federation_reporting`, `sports_federation_finance_bridge`, `sports_federation_public_site`, `sports_federation_import_tools`.
Work already landed: integration contract registry records, partner tokens with per-contract subscriptions, partner manifest discovery, token-authenticated finance-event handoff delivery, explicit route hints and deprecation metadata, and operator-visible backend management views.
Done when: downstream systems can integrate through explicit partner interfaces rather than shared backend sessions or ad hoc CSV pulls.

2. Done (2026-04-12): Add inbound integration orchestration beyond manual CSV onboarding.
Modules: `sports_federation_import_tools`, `sports_federation_notifications`, `sports_federation_reporting`.
Work already landed: staged inbound delivery records, checksum-based duplicate reuse, partner API delivery endpoints, direct handoff into preview wizards, governance-job linkage, synchronized preview/approval/process/failure states, and focused regression coverage.
Done when: repeated third-party data exchange can be operated through the same governed import pipeline already used for rollover work.

## Year 3 Sequencing Guidance

Recommended execution order:

1. Referee self-service assignment response.
2. Unified club operations workspace for active tournaments.
3. Self-service compliance renewal and remediation submission.
4. Editorial publication scheduling and season-wide public discovery.
5. Managed partner-authenticated integrations and staged inbound deliveries.

Priority 0 through Priority 2 are now complete for the Year 3 scope.

Current Year 3 execution batch completed in this pass:

1. Done (2026-04-12): Ship referee self-service assignment response in the portal with focused portal regression coverage.
2. Done (2026-04-12): Ship the unified club tournament workspace for active tournaments with registration, roster, match-day, and result follow-up visibility.
3. Done (2026-04-12): Ship self-service compliance submission and renewal workflows with portal-scoped remediation visibility.
4. Done (2026-04-12): Ship season discovery, editorial scheduling, and safer public team follow surfaces.
5. Done (2026-04-12): Ship managed partner integrations and staged inbound deliveries on top of the governed import pipeline.

## Year 4 Overview — Intelligence, Planning, and Scale

Year 4 should focus on federation-wide planning and operational intelligence on
top of the reporting, exception, and reconciliation surfaces already present.
Reporting should evolve from exports and queues into decision support,
compliance and governance should produce audit-grade traces with historical
trend analysis, and cross-season analysis should support strategic planning,
budgeting, and performance monitoring.

Target outcome: the platform becomes not just a workflow system, but a planning
and insight system for the federation.

Current Year 4 execution batch completed in this pass:

1. Done (2026-04-13): Added season planning targets to the core season model and extended the governed season CSV import contract to carry planning baselines safely.
2. Done (2026-04-13): Added season-scoped finance actuals and season budgets so planned vs actual spend can be monitored from the federation workflow layer.
3. Done (2026-04-13): Added immutable compliance history archives so requirement status changes can be audited over time.
4. Done (2026-04-13): Added governance override outcome logging so implemented decisions now carry post-decision evidence.
5. Done (2026-04-13): Added season portfolio and club performance reporting, including scheduled CSV generation through the existing reporting scheduler.

Current Year 4 verification status:

1. Done (2026-04-13): Focused CI verification passed for `sports_federation_base`, `sports_federation_import_tools`, `sports_federation_finance_bridge`, `sports_federation_compliance`, `sports_federation_governance`, and `sports_federation_reporting`.

## Ongoing Quality Gates For Every Year

1. Every workflow change must come with tests.
2. Every new model or field change must come with ACL and manifest review.
3. Every behavior change must update the relevant workflow or README.
4. Every integration change must remain env-driven and CI-safe.
5. Every release candidate must include migration notes and rollback guidance.
