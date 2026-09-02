# Sports Federation Platform Roadmap

Last updated: 2026-09-02
Owner: Federation Platform Team
Last reviewed: 2026-09-02
Review cadence: Every release
Release train: 2026.08
Planning horizon: 12 months
Scope: All federation addons, shared CI, documentation, runbooks, and release operations

## Product Direction

The platform has broad federation coverage and strong technical safeguards. The next release cycle must prioritize simpler operator workflows, clearer ownership boundaries, and production evidence over additional domain breadth.

## Delivery Principles

- Keep internal audit, security, revision, and concurrency safeguards.
- Hide technical implementation concepts from normal club and tournament users.
- Use guided defaults for common workflows and progressive disclosure for expert controls.
- Keep every privileged portal write behind a model-owned scope check.
- Treat migrations, restore readiness, observability, and documentation as release gates.
- Prefer one authoritative document per concern. Delete completed mini-roadmaps and generated snapshots that duplicate tests or code.

## Delivery Roadmap

The executable milestone sequence is maintained in
[`docs/DELIVERY_ROADMAP.md`](docs/DELIVERY_ROADMAP.md). This repository roadmap
remains the priority and policy source; the delivery roadmap defines concrete
deliverables, automation, and exit criteria.

## Current Priorities

### P0: Simplify competition and portal workflows

Status: In progress

- Provide template-led setup for league, tournament-day, and cup formats.
- Reduce user-facing lifecycle language to Draft, Ready, Live, and Finished while retaining richer internal states.
- Keep stage graphs, schedule revisions, fairness tuning, and shared-day controls behind Advanced tools.
- Make normal schedules preparable without manually managing stages, rounds, or progression mappings.
- Keep the club portal task-first: teams, registrations, upcoming matches, and action items.

Success criterion: a normal competition can be configured, scheduled, and published without users understanding the underlying Odoo data model.

### P0: Maintain competition ownership boundaries

Status: Complete for the current release

- Keep registration, format, calendar, scheduling, schedule approval, and
	match-day operations as explicit handovers.
- Keep fairness, validation, publication, and operational commands in their
	owning modules rather than recreating a shared orchestration facade.
- Preserve immutable published snapshots, audit events, and optimistic
	concurrency guards while extending the flow.

### P0: Release and migration confidence

Status: In progress

- Keep strict lint, workflow-contract, constraint/index, OpenAPI, migration-evidence, and dependency-drift checks green.
- Run module upgrades against a production-like database copy.
- Record backup, restore, rollback, and migration evidence for each release candidate.
- Resolve dependency-drift warnings before release, even when they are non-blocking.

### P0: Security and ownership boundaries

Status: Ongoing

- Maintain negative cross-club and direct-ID access tests for every portal write route.
- Keep elevated access centralized in `federation.portal.privilege`.
- Extend secret redaction, token rotation, upload scanning, and audit-event coverage.
- Require a security review for every new public, portal, or partner integration route.

### P1: Background-job reliability

Status: Planned

- Standardize retry and backoff behavior.
- Add dead-letter and operator recovery surfaces.
- Alert on stale or repeatedly failing scheduled actions.
- Link failures through correlation IDs.

### P1: Retention evidence

Status: Partially complete

Default cleanup windows and scheduled actions exist for notification logs, inbound deliveries, and generated report artifacts. Remaining work is evidence and exception visibility.

- Test policy-to-code retention mappings.
- Surface last run, deleted count, and exceptions.
- Include retention health in release readiness.

### P1: Test strategy and CI runtime

Status: In progress

- Maintain smoke, contract, focused-module, and release-candidate tiers.
- Keep ownership, optimistic-concurrency, migration, and production-like
	restore-drill checks mandatory.
- Pin lint-tool versions so local and CI behavior remain identical.
- Track suite runtime and quarantine only with an owner and expiry date.

### P1: Documentation governance

Status: In progress

- Keep `ROADMAP.md`, `ROUTE_INVENTORY.md`, `INTEGRATION_CONTRACTS.md`, `DATA_RETENTION_POLICY.md`, and accepted ADRs within their freshness budget.
- Update documentation in the same change as routes, contracts, state transitions, retention, or architecture decisions.
- Prefer durable policy documents over one-line release-candidate roadmaps.

### P2: Accessibility and usability

Status: Planned

- Add route-level accessibility checks for primary portal and public journeys.
- Cover keyboard-only planner and operations-board scenarios.
- Add terminology consistency checks for user-facing labels.
- Expand deterministic training and sandbox scenarios.

### P2: Operational dashboards

Status: Planned

- Consolidate release gates, job health, retention evidence, integration failures, and recovery readiness.
- Provide actionable remediation links rather than passive status metrics.

## Completed Foundations

The repository already contains substantial foundations that should be maintained rather than reimplemented:

- workflow state contract validation
- constraint and index contract validation
- migration review evidence checks
- OpenAPI contract validation
- portal ownership and negative access suites
- result-control separation of duties
- schedule revisions, optimistic concurrency, idempotency, and planner history
- versioned extension contracts and fault isolation
- correlation IDs in key operational paths
- performance smoke and production-like tournament simulations

## Release Review Checklist

At every release:

1. Re-rank current priorities using incidents, operator feedback, and test evidence.
2. Move genuinely completed work to release notes rather than growing a permanent completed backlog here.
3. Review contract deprecations and target dates.
4. Review route ownership, ADRs, retention, and dependency drift.
5. Record any deferred P0 item with an owner, reason, and target release.
