# Sports Federation Platform Roadmap

Last updated: 2026-06-01
Owner: Federation Platform Team
Planning horizon: 18 months
Scope: All addons, shared CI/docs/runbooks, and release operations

## Planning Principles

1. Keep workflow correctness first for tournament lifecycle, match-day operations, and result officiality.
2. Prefer small, test-backed, module-bounded changes over cross-cutting rewrites.
3. Strengthen extension seams before introducing new domain complexity.
4. Treat release reliability, restore readiness, and observability as product features.
5. Keep portal and public surfaces safe-by-default on ownership and publication rules.

## Prioritization Model

- P0: Correctness, security, and release blockers.
- P1: High-value throughput and maintainability improvements.
- P2: Product-quality and analytics improvements.
- P3: Exploratory and optimization opportunities.

## Delivery Windows

- Wave 1: 0-3 months
- Wave 2: 3-6 months
- Wave 3: 6-12 months
- Wave 4: 12-18 months

---

## Detailed Plan (20 Items)

### 1) Workflow Source-of-Truth Validation Gate
- Priority: P0
- Wave: 1
- Status: Done (2026-06-01; verified by CI run 20260601_071414 and strict lint gate)
- Why now: Workflow markdown and implemented states can drift as modules evolve.
- Scope: Add CI checks that compare canonical workflow state transitions against model selection values and guarded actions.
- Deliverables:
  - Workflow-state mapping file per domain workflow.
  - CI validator integrated into the lint/hygiene stage.
  - Failing examples and fix guidance in contributor docs.
- Success metric: Zero undocumented state additions in release branches.

### 2) Competition Workspace Service Final Decomposition
- Priority: P0
- Wave: 1
- Status: Done (2026-06-01; verified by CI run 20260601_071414 and strict lint gate)
- Why now: Core service is improved but still carries high cognitive load and broad change surface.
- Scope: Split remaining orchestration paths into cohesive mixins and helper services, aligned by read, write, and planner state concerns.
- Deliverables:
  - Additional focused service seams with explicit responsibilities.
  - Reduced method count per class and smaller file size targets.
  - Regression coverage for each seam boundary.
- Success metric: Lower review time and smaller median diff size for workspace changes.

### 3) Workspace Extension Contract v2
- Priority: P0
- Wave: 1
- Status: Done (2026-06-01; verified by CI run 20260601_071414 and strict lint gate)
- Why now: Extension hooks exist, but long-term compatibility needs explicit schema lifecycle and deprecation behavior.
- Scope: Define extension contract versions, fallback behavior, and validation tooling for hook payloads/issues/score components.
- Deliverables:
  - Contract specification document and migration policy.
  - Runtime warnings upgraded to actionable diagnostics.
  - Contract test suite per extension hook type.
- Success metric: No breaking extension regressions across two release trains.

### 4) Scheduler Performance Baseline Program
- Priority: P1
- Wave: 1
- Status: Done (2026-06-01; verified by CI run 20260601_071414 and strict lint gate)
- Why now: Planner adoption is rising and needs predictable response under larger event loads.
- Scope: Build deterministic benchmark scenarios for slot generation, assignment, swap, undo/redo, and auto-schedule.
- Deliverables:
  - Benchmark dataset pack.
  - CI performance smoke thresholds.
  - Baseline report updates per release.
- Success metric: P95 planner payload and assignment latency within target budgets.

### 5) Database Constraint and Index Audit
- Priority: P0
- Wave: 1
- Status: Done (2026-06-01; verified by strict lint gates and CI run 20260601_073151)
- Why now: Cross-module growth increases risk of soft-validated invariants and query regressions.
- Scope: Audit major models for unique constraints, foreign-key semantics, and index coverage on common filters.
- Deliverables:
  - Constraint/index gap report.
  - Migration scripts for schema hardening.
  - Post-migration data-fix scripts where needed.
- Success metric: Reduced data-quality incidents and improved heavy-query plans.

### 6) Migration Discipline and Dry-Run Enforcement
- Priority: P0
- Wave: 1
- Status: Done (2026-06-01; verified by strict lint gates and CI run 20260601_073151)
- Why now: Release reliability depends on predictable schema/data migration behavior.
- Scope: Require migration review checks for model/view/controller ownership changes, with dry-run evidence in release PRs.
- Deliverables:
  - Stronger CI migration-review gate.
  - Migration checklist templates.
  - Rollback notes per migration-sensitive change.
- Success metric: Zero production rollbacks caused by migration defects.

### 7) Portal Ownership Boundary Hardening
- Priority: P0
- Wave: 1
- Status: Done (2026-06-01; verified by strict lint gates and CI run 20260601_073151)
- Why now: Portal privilege paths are high-risk for access regressions when features are added.
- Scope: Expand negative and escalation tests across representative, team-scoped, and official-scoped flows.
- Deliverables:
  - Ownership test matrix across portal controllers and model helpers.
  - Deny-by-default regression tests for missing scope filters.
  - Coverage dashboard for ownership-sensitive routes.
- Success metric: No cross-club data exposure regressions in post-install suites.

### 8) Result Pipeline Separation-of-Duties Reinforcement
- Priority: P0
- Wave: 1
- Status: Done (2026-06-01; verified by strict lint gates and CI run 20260601_073151)
- Why now: Submit, verify, and approve guards must remain strict as portal/internal action paths evolve.
- Scope: Harden action-level role checks and audit traces, including contest/correction recovery loops.
- Deliverables:
  - Explicit duty-separation assertions.
  - Additional contested/corrected loop tests.
  - Improved operator-facing error messaging.
- Success metric: Zero bypasses of approval-duty boundaries.

### 9) Standings Recompute Queue and Idempotency
- Priority: P1
- Wave: 2
- Status: Done (2026-06-01; verified by CI run 20260601_080437, strict lint gate, and focused import-tools suite run)
- Why now: Synchronous recompute paths can become brittle under higher update volume.
- Scope: Introduce optional queued recompute with idempotent jobs and conflict-safe replay.
- Deliverables:
  - Queue model and worker orchestration.
  - Idempotency keys for recompute requests.
  - Operational visibility into pending/failed recomputes.
- Success metric: Stable recompute behavior under bursty result updates.

### 10) End-to-End Correlation ID Standard
- Priority: P1
- Wave: 2
- Status: Done (2026-06-01; verified by CI run 20260601_080437 and strict lint gate)
- Why now: Multi-module workflows are difficult to debug without request-to-job traceability.
- Scope: Propagate correlation IDs through controllers, services, planner writes, scheduled jobs, and notifications.
- Deliverables:
  - Correlation ID helper utilities.
  - Log format standard update.
  - Incident debugging runbook section.
- Success metric: Faster root-cause analysis for cross-module failures.

### 11) Reporting Query Modernization
- Priority: P1
- Wave: 2
- Status: Done (2026-06-01; verified by CI run 20260601_080437 and strict lint gate)
- Why now: Deprecation warnings and heavy report surfaces indicate future compatibility and performance risk.
- Scope: Replace deprecated read_group usage and optimize high-traffic reporting builders.
- Deliverables:
  - Reporting query refactors with benchmark evidence.
  - Explain-snapshot updates for key reporting paths.
  - Compatibility note in release docs.
- Success metric: No deprecation warnings in reporting test runs.

### 12) Integration API Contract Verification Expansion
- Priority: P1
- Wave: 2
- Status: Done (2026-06-01; verified by CI run 20260601_080437 and strict lint gate)
- Why now: Contract drift between OpenAPI docs and runtime payloads is a recurring integration risk.
- Scope: Add contract tests for request/response schema, auth failures, pagination, and error shape consistency.
- Deliverables:
  - OpenAPI-backed contract suite in CI.
  - Golden examples for partner onboarding.
  - Compatibility policy per endpoint version.
- Success metric: No partner-facing contract regressions between minor releases.

### 13) Cron and Background Job Reliability Program
- Priority: P1
- Wave: 2
- Why now: Operational correctness depends on scheduled tasks finishing reliably and observably.
- Scope: Add retry policies, dead-letter handling, and operator-facing dashboards for recurring jobs.
- Deliverables:
  - Standard retry/backoff helpers.
  - Failed-job queue inspection UI.
  - Alert thresholds and runbook actions.
- Success metric: Reduced unresolved scheduled-job failure backlog.

### 14) Security Posture Hardening Sprint
- Priority: P0
- Wave: 2
- Why now: Expanding integrations and portal surfaces increase secret-handling and privilege risks.
- Scope: Strengthen secret redaction tests, token rotation workflows, and privilege escalation guardrails.
- Deliverables:
  - Secret scanning gates and redaction assertions.
  - Token lifecycle policy enforcement checks.
  - Access-rule regression pack for sensitive models.
- Success metric: No secret leaks in logs/artifacts; no critical access-rule findings.

### 15) Data Retention Automation and Evidence
- Priority: P1
- Wave: 2
- Why now: Retention behavior spans notifications, imports, and report artifacts and needs auditable consistency.
- Scope: Standardize retention cron behavior and capture retention evidence in health dashboards.
- Deliverables:
  - Retention policy-to-cron mapping table.
  - Automated retention verification tests.
  - Operator checklist for retention exceptions.
- Success metric: Retention jobs consistently pass and produce auditable evidence.

### 16) Accessibility and Usability Compliance Pack
- Priority: P1
- Wave: 3
- Why now: Portal and public flows are critical user entry points and must remain inclusive as features grow.
- Scope: Add route-level accessibility checks, keyboard path tests, and usability copy consistency checks.
- Deliverables:
  - Accessibility CI checks for major portal/public templates.
  - Keyboard-only test scenarios for operations board and workspace.
  - Terminology consistency lints.
- Success metric: Reduced accessibility defects in release QA.

### 17) Test Strategy Tiering and Runtime Reduction
- Priority: P1
- Wave: 3
- Why now: Suite growth increases release-cycle cost and feedback latency.
- Scope: Tier tests into smoke, contract, focused module, and broad release surfaces with clear ownership.
- Deliverables:
  - Updated suite matrix and ownership map.
  - Flaky-test quarantine and stabilization policy.
  - Runtime target budgets by suite tier.
- Success metric: Faster average CI feedback without coverage regression.

### 18) Demo and Sandbox Scenario Expansion
- Priority: P2
- Wave: 3
- Why now: Training, onboarding, and QA need richer deterministic scenarios for advanced workflows.
- Scope: Extend demo pack to include contested results, override flows, shared-day exceptions, and governance recovery cases.
- Deliverables:
  - Expanded demo data fixtures.
  - Scenario walkthrough docs.
  - Demo integrity tests.
- Success metric: Shorter onboarding time and higher reproducibility in bug triage.

### 19) Incident Response and Recovery Maturity
- Priority: P1
- Wave: 4
- Why now: More automation and integrations require faster, clearer incident handling.
- Scope: Build incident playbooks for planner, portal, reporting, and integration outage classes.
- Deliverables:
  - Incident playbook library linked to runbook.
  - Automated incident context bundle scripts.
  - Recovery drills with measurable outcomes.
- Success metric: Lower mean time to detect and resolve major incidents.

### 20) Release Governance Dashboard
- Priority: P2
- Wave: 4
- Why now: Release readiness signals are currently distributed across docs, CI logs, and ad hoc checks.
- Scope: Consolidate release gates, doc freshness, migration checks, and suite status into a single decision dashboard.
- Deliverables:
  - Release readiness scorecard.
  - Blocker classification and sign-off workflow.
  - Historical trend tracking for release quality.
- Success metric: Higher first-pass release acceptance rate.

---

## Idea Backlog (80 Items)

21) Enforce ADR freshness cadence for high-impact architectural changes.
22) Auto-generate state-machine diagrams from model selections and transition helpers.
23) Add optional-manifest dependency consistency checks across addon families.
24) Add model ownership annotations for easier code stewardship.
25) Introduce a cross-module deprecation lifecycle policy with sunset tracking.
26) Auto-sync query budgets from benchmark snapshots into CI assertions.
27) Publish a shared fixture catalog package for common federation test setups.
28) Add deterministic random-seed helpers for schedule-generation tests.
29) Introduce flaky-test quarantine workflow with owner escalation.
30) Add strict portal ownership contract tests for sudo/elevated execution paths.
31) Standardize API pagination and sorting semantics across integration endpoints.
32) Publish endpoint-level rate-limit policy matrix with test enforcement.
33) Add signed webhook replay protection with nonce window checks.
34) Build OpenAPI example drift checker against runtime responses.
35) Add dead-letter queue interface for failed inbound import deliveries.
36) Version inbound import schemas and add migration handlers.
37) Build a unified background job operations dashboard.
38) Add cron drift detection and stale-run alerting.
39) Define service-level objectives per critical module flow.
40) Add optional structured JSON logging mode for production diagnostics.
41) Introduce secret redaction test suite for logs and notifications.
42) Add backup freshness monitor with release gate integration.
43) Automate monthly restore drills and evidence capture.
44) Build attachment malware-scan policy simulator for safe tuning.
45) Introduce per-environment feature flags for progressive delivery.
46) Add dark-launch hooks for planner behavior changes.
47) Normalize audit-event taxonomy across modules.
48) Propagate correlation IDs through all portal controller responses.
49) Add trace exporter integration for distributed observability.
50) Create a standard large-event performance profile dataset.
51) Add cold-start benchmark for module installation and upgrade paths.
52) Add warm-cache benchmark for planner and portal payload endpoints.
53) Explore materialized-view strategy for heavy reporting projections.
54) Add SQL style and safety lint rules for reporting views.
55) Complete read_group to _read_group modernization across modules.
56) Add memory-budget guards for heavy report generation jobs.
57) Add retention-drill tests for report artifacts and generated files.
58) Add incremental standings recompute mode for small result updates.
59) Add asynchronous standings recompute queue with idempotent retries.
60) Build standings reconciliation explain view for operators.
61) Add SLA timers for result verification and approval handoffs.
62) Build a contested-result resolution assistant wizard.
63) Add referee assignment fairness scoring at tournament-day level.
64) Add referee availability conflict heatmap for assignment planning.
65) Add roster-deadline calendar synchronization for club reps.
66) Add match-sheet completeness scoring for pre-match readiness.
67) Automate player-license expiry communication campaigns.
68) Add a club compliance readiness index surface in portal and reporting.
69) Build governance-override guidance assistant for operators.
70) Add recurring venue-blackout templates and conflict previews.
71) Add travel-buffer constraint plugin for schedule scoring.
72) Add shared-gameday load-balancing suggestions across courts.
73) Add planner what-if sandbox mode without persistent writes.
74) Add bulk-action dry-run preview with projected warnings/conflicts.
75) Add planner conflict-resolver UI for stale optimistic-lock writes.
76) Add planner keyboard shortcut discovery overlay.
77) Add mobile offline draft capability for portal score entry.
78) Add guided-mode steps for first-time portal operators.
79) Add accessibility compliance gates for core portal routes.
80) Add multilingual terminology consistency checks for UI labels.
81) Add public-site SEO slug health monitoring and conflict alerts.
82) Add deterministic public cache invalidation hooks after publication.
83) Add privacy-review checklist enforcement for public profile fields.
84) Add public route canary tests for release-day confidence.
85) Add notification template versioning and rollback support.
86) Build notification deliverability analytics dashboard.
87) Add channel fallback rules for failed notifications.
88) Add finance-reconciliation assistant with actionable remediation hints.
89) Add sanction-to-finance linkage consistency validator.
90) Add payment-provider abstraction interface for future integrations.
91) Build module scaffolding generator v2 with tests/docs wiring.
92) Enforce module path ownership checks from ownership registry.
93) Add docs freshness bot triggered by changed modules.
94) Expand workflow documentation with executable scenario examples.
95) Add release-notes auto-assembler from commit and module metadata.
96) Add dependency vulnerability scan gate in CI.
97) Add secret-scanning pre-push hook recommendations and templates.
98) Add branch-protection compliance reporter for release branches.
99) Run quarterly architecture scorecard review and publish deltas.
100) Build continuous operator-feedback ingestion loop into roadmap triage.

---

## Suggested Execution Sequence

1. Execute items 1-8 in Wave 1 as the foundation tranche.
2. Execute items 9-15 in Wave 2 to improve reliability and scale readiness.
3. Execute items 16-18 in Wave 3 to improve user quality and delivery throughput.
4. Execute items 19-20 in Wave 4 to institutionalize operational maturity.
5. Pull from the 80-item idea backlog each release based on measurable bottlenecks, incident learnings, and owner capacity.

## Operating Cadence

- Monthly: Prioritize top 5 roadmap candidates by risk and impact.
- Per release: Move completed roadmap items into release notes and archive.
- Quarterly: Re-rank the 80-item idea backlog with updated telemetry and incident trends.
