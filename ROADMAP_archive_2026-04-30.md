# ROADMAP — 2026-04-17 Improvement Program

Last updated: 2026-04-19
Owner: Federation Platform Team
Last reviewed: 2026-04-19
Review cadence: Every release
Release train: 2026.04

The previous operating-period roadmap is archived in `ROADMAP_archive_2026-04-17.md`.
This roadmap is driven by the 2026-04-17 code review and shifts the focus from
feature completion to hardening, simplification, and long-term operability.

## Period Goal

Lower trust-boundary risk and reduce the cost of change across portal,
reporting, compliance, and integration workflows.

## Review Baseline

- 19 custom addons, 252 Python files, 132 XML files, and 66 test files.
- 178 `sudo()` usages, 51 `with_user(user).sudo()` patterns, 24 public route declarations, and 7 `csrf=False` declarations.
- The highest complexity is concentrated in reporting, roster workflows, public competition routes, and compliance target handling.
- CI exists and is useful, but lint coverage is still scoped to a hand-picked subset of files.
- Migration handling exists, but only one explicit migration script was found despite recent cross-module structural churn.

## Guiding Principles

- Prefer shrinking risky surfaces over shipping additional breadth.
- Replace repeated trust-boundary code with shared, testable abstractions.
- Split files when one concern can no longer be reviewed comfortably in one sitting.
- Archive time-sensitive documents when they are superseded.
- Tie every security or workflow change to focused regression tests.

## Phase 1 — First 2 Weeks: Trust Boundary Hardening

1. [x] Harden partner authentication.
Modules: `sports_federation_import_tools`.
Work: remove query-string credentials, accept secrets only from headers or authorization metadata, hash tokens at rest, and document/execute a rotation plan for existing tokens.
Done when: no controller accepts `access_token` or `partner_code` from request params, and operator guidance exists for rotating previously issued tokens.

2. [x] Add upload and payload guardrails.
Modules: `sports_federation_import_tools`, `sports_federation_compliance`, shared attachment policies.
Work: enforce maximum payload size, allowlisted MIME and extension rules, checksum dedupe, and consistent user-facing validation messages.
Done when: oversized or disallowed files are rejected consistently in partner and portal flows with automated tests.

3. [x] Centralize privileged portal writes.
Modules: `sports_federation_portal`, `sports_federation_compliance`, `sports_federation_public_site`.
Work: introduce one shared portal privilege boundary helper for access checks and elevated writes, then refactor current helpers to use it.
Done when: new privileged portal writes go through one shared abstraction and legacy helpers have contract tests around ownership and state transitions.

## Phase 2 — Weeks 3 To 5: Complexity Extraction

1. [x] Split reporting SQL monoliths.
Modules: `sports_federation_reporting`.
Work: separate `report_operational.py` into report-specific files, add named SQL block headers, and add report-specific invariants in tests.
Done when: no single reporting model file exceeds roughly 400 lines without a clear reason.

2. [x] Break down roster and portal controller monoliths.
Modules: `sports_federation_portal`, `sports_federation_rosters`.
Work: split `controllers/rosters.py` and the broad portal controller into narrower workflow files, and factor redirect, scope-loading, and form-error patterns into shared helpers.
Done when: primary portal controllers are materially smaller and route behavior remains covered by smoke and service tests.

3. [x] Simplify compliance target resolution.
Modules: `sports_federation_compliance`.
Work: extract shared target field maps and target resolution into one reusable layer.
Done when: adding a new compliance target type requires one obvious extension point rather than synchronized edits in multiple classes.

## Phase 3 — Weeks 6 To 8: Readability And Engineering Discipline

1. [x] Improve docstring and method-shape standards.
Modules: repository-wide.
Work: replace low-signal `Handle X flow` docstrings in hotspots with invariants, side effects, and security assumptions, and continue breaking up methods with more than one clear responsibility.
Done when: portal, compliance, and reporting hotspots explain why and under which assumptions they operate.

2. [x] Expand CI quality gates beyond a hand-picked file list.
Modules: repository-wide, `ci`.
Work: widen Black and Flake8 coverage in stages, starting with a non-blocking full-repo lint job and then gating after debt is reduced.
Done when: the repository no longer depends on narrow `BLACK_PATHS` and `FLAKE8_PATHS` allowlists for normal maintenance.

3. [x] Add documentation freshness rules.
Modules: repository-wide.
Work: add owner/date metadata to review, roadmap, and architecture documents and make them part of release preparation.
Done when: time-sensitive documents are archived or refreshed during the release cadence instead of drifting.

## Phase 4 — Weeks 9 To 12: Operability, Performance, And Upgrade Safety

1. [x] Add performance baselines for public and reporting hotspots.
Modules: `sports_federation_public_site`, `sports_federation_reporting`, `sports_federation_portal`.
Work: baseline expensive public routes and large SQL reports, capturing query counts and slow operators.
Done when: the slowest public and reporting endpoints have known budgets and regressions can be detected early.

2. [x] Tighten migration discipline.
Modules: repository-wide.
Work: require migration impact review for model, view, and route ownership changes and add module-local migration scripts where needed.
Done when: upgrade-sensitive changes are not shipped without explicit migration handling or release notes.

3. [x] Improve failure typing and operator feedback.
Modules: `sports_federation_notifications`, `sports_federation_reporting`, `sports_federation_import_tools`.
Work: replace broad exception storage with typed failure categories and sanitized operator messages.
Done when: retryable delivery, import, and report failures are distinguishable from developer defects.

## Suggested Sequence

1. Integration credential hardening and upload guardrails.
2. Shared portal privilege abstraction.
3. Reporting file split and compliance target resolver.
4. Portal controller decomposition.
5. CI and documentation freshness expansion.
6. Performance baselines, migration discipline, and typed failure handling.

## Exit Criteria

- No secret-bearing integration flow accepts credentials via query string.
- No public or portal upload path lacks file-size and file-type validation.
- New privileged portal writes use one shared abstraction with tests.
- Reporting and portal hotspot files are materially smaller and easier to review.
- Time-sensitive roadmap and review documents stop drifting beyond one operating period.
- Upgrade-sensitive changes have explicit migration handling.

## Twenty Additional Improvements

1. [x] Publish an OpenAPI-style contract document for partner integration routes and payloads.
2. [x] Introduce one-time token reveal plus last-four-character token display in the back office.
3. [x] Add rate limiting or throttling for public JSON and partner integration endpoints.
4. [x] Add attachment antivirus or external malware-scanning hooks for uploaded files.
5. [x] Implement pagination or incremental cursors for finance event exports.
6. [x] Add idempotency keys for inbound delivery submissions.
7. [x] Add architecture decision records for portal trust boundaries, reporting SQL views, and public route ownership.
8. [x] Add a repo-wide dead-link and stale-doc check in CI.
9. [x] Add smoke tests that verify every public route listed in `ROUTE_INVENTORY.md` still resolves.
10. [x] Add per-module ownership metadata to manifests or a central owner registry.
11. [x] Add data-retention policies for logs, staged deliveries, and generated report files.
12. [x] Add a backup-restore drill script and a periodic restore verification checklist.
13. [x] Add slow-query logging and `EXPLAIN` snapshots for the largest SQL views.
14. [x] Add accessibility review passes for portal and public templates.
15. [x] Add mobile-specific template checks for the largest portal workflows.
16. [x] Add a deterministic demo-data pack for end-to-end federation walkthroughs.
17. [x] Add audit dashboards for privileged portal actions and token rotations.
18. [x] Add import wizard base classes for row parsing, duplicate detection, and reusable error taxonomy.
19. [x] Add shared enums or helper predicates for cross-module workflow states where semantics are reused.
20. [x] Add a release train and versioning convention so roadmap, migrations, and runbooks share one cadence.
