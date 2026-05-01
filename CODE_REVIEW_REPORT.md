# CODE REVIEW REPORT — 2026-04-17

Owner: Federation Platform Team
Last reviewed: 2026-04-17
Review cadence: Every release

This report supersedes the earlier snapshot and reflects the repository as it
exists today. The previous report had drifted from the codebase in a few
important places, especially around CI, requirements, and test coverage. That
documentation drift is itself part of the maintainability review below.

## Scope

- Focus areas: maintainability, readability, and security.
- Review method: static review of repository structure, representative high-complexity files, controller and model trust boundaries, CI and developer tooling, and existing test coverage.
- Not included: full suite execution, live browser validation, load testing, or a dedicated penetration test.

## Executive Summary

The project is in materially better shape than the previous review suggested.
It has a strong documentation culture, broad test coverage, a working CI
pipeline, and clear module boundaries. The main risk is no longer missing basic
engineering hygiene. The main risk is that complexity and trust-boundary logic
are now concentrated in a small set of files and patterns:

- reporting logic is packed into a few very large SQL-view and report-scheduling files;
- portal and compliance flows depend on repeated `with_user(user).sudo()` patterns plus hand-written ownership checks;
- integration endpoints accept credentials and payloads in ways that are functional but not hardened enough for long-term exposure.

Overall assessment:

- Maintainability: medium risk.
- Readability: medium risk.
- Security: medium-high risk on a small number of specific surfaces.
- Delivery readiness: good foundation, but the next operating period should prioritize hardening and simplification over feature expansion.

## Current Strengths

- All 19 custom addons currently have automated tests in the repository.
- The repository has strong operational and workflow documentation, including `CONTEXT.md`, `TECHNICAL_NOTE.md`, inventories, and runbooks.
- CI exists under `.github/workflows/ci.yml` and already runs lint plus multiple Odoo test suites.
- The codebase already moved several privileged controller writes into model-level portal helpers, which is the right architectural direction.
- Public tournament description rendering appears to have moved away from the older raw-HTML pattern; the current templates use `t-field` rather than `t-raw`.

## Review Signals

_Last updated: 2026-04-28 (Phase 4 refresh)_

- 20 custom addons.
- 328 Python files (47 195 lines).
- 138 XML files (13 591 lines).
- 59 test files (19 413 test lines).
- `except Exception` occurrences: 7 (all with `build_failure_feedback` / `is_safe_operator_detail` sanitization; notifications and import handlers).
- `auth="public"` route declarations: 24.

Largest complexity hotspots by line count (production code only):

- [sports_federation_public_site/models/public_flags.py](sports_federation_public_site/models/public_flags.py) — 1 001 lines.
- [sports_federation_rosters/models/team_roster.py](sports_federation_rosters/models/team_roster.py) — 585 lines.
- [sports_federation_reporting/models/report_schedule.py](sports_federation_reporting/models/report_schedule.py) — 319 lines.
- [sports_federation_reporting/models/report_operational.py](sports_federation_reporting/models/report_operational.py) — 219 lines.
- [sports_federation_public_site/controllers/public_competitions.py](sports_federation_public_site/controllers/public_competitions.py) — 734 lines.

## Findings

### High Severity

1. Integration credentials can be transported via query parameters.

Evidence:

- [sports_federation_import_tools/controllers/integration_api.py](sports_federation_import_tools/controllers/integration_api.py) reads `partner_code` and `access_token` from `request.params` when headers are absent.

Why it matters:

- Query parameters leak into reverse-proxy logs, browser history, analytics systems, support screenshots, and copied URLs.
- This is an avoidable exposure for long-lived partner credentials.

Recommendation:

- Accept credentials only from headers or an authorization scheme.
- Reject query-string tokens outright.
- Rotate existing partner tokens after the change.

2. Partner API tokens are stored and compared as plaintext application secrets.

Evidence:

- [sports_federation_import_tools/models/integration_gateway.py](sports_federation_import_tools/models/integration_gateway.py) stores `auth_token` in a plain `fields.Char` and compares it directly in `authenticate_partner()`.
- [sports_federation_import_tools/views/integration_partner_views.xml](sports_federation_import_tools/views/integration_partner_views.xml) masks the field in the form, but masking in the UI does not change storage semantics.

Why it matters:

- A database export or administrative mistake exposes live credentials immediately.
- It prevents one-way verification and safe audit display patterns.

Recommendation:

- Store token hashes, not raw tokens.
- Reveal generated tokens only once.
- Show only non-sensitive metadata such as creation time, rotation time, and last four characters.

3. Inbound delivery and portal upload flows do not enforce payload size or file-type guardrails.

Evidence:

- [sports_federation_import_tools/models/integration_gateway.py](sports_federation_import_tools/models/integration_gateway.py) decodes arbitrary base64 input and stores it as an attachment without a size check.
- [sports_federation_compliance/models/document_submission.py](sports_federation_compliance/models/document_submission.py) accepts uploaded files and creates attachments without size, MIME, or extension validation.

Why it matters:

- These paths are exposed to partner systems and portal users.
- They create storage and memory denial-of-service risk, malware carriage risk, and retention cost growth.

Recommendation:

- Introduce one shared upload policy with maximum size, MIME and extension allowlists, checksum dedupe, and optional antivirus integration.
- Add explicit user-facing validation messages and tests for rejected content.

4. Elevated portal writes rely on distributed ownership checks rather than one consistent boundary.

Evidence:

- 51 `with_user(user).sudo()` patterns appear across portal and compliance helpers.
- Representative examples are in [sports_federation_portal/models/federation_tournament_registration.py](sports_federation_portal/models/federation_tournament_registration.py), [sports_federation_portal/models/federation_match_referee.py](sports_federation_portal/models/federation_match_referee.py), [sports_federation_portal/models/federation_team_roster.py](sports_federation_portal/models/federation_team_roster.py), and [sports_federation_compliance/models/document_submission.py](sports_federation_compliance/models/document_submission.py).

Why it matters:

- The current code is mostly careful, but the pattern is fragile.
- One future helper that forgets an ownership or state check becomes a real authorization defect.

Recommendation:

- Create a shared portal privilege boundary abstraction with standard access assertions and elevated-write helpers.
- Keep ownership and state contract tests close to that abstraction.

### Medium Severity

5. Reporting SQL is too concentrated in one file and one abstraction layer.

Evidence:

- [sports_federation_reporting/models/report_operational.py](sports_federation_reporting/models/report_operational.py) is 968 lines and defines multiple SQL-backed reports in one place.

Why it matters:

- Schema changes, performance tuning, and review become slow and error-prone.
- Regression analysis is harder because unrelated report logic shares one large file.

Recommendation:

- Split report models by report domain.
- Add named SQL block headers and explicit invariants per report in tests.

6. Report scheduling mixes orchestration, rendering, persistence, and failure handling.

Evidence:

- [sports_federation_reporting/models/report_schedule.py](sports_federation_reporting/models/report_schedule.py) builds report payloads, serializes CSV, stores generated files, updates scheduling metadata, and handles failures.

Why it matters:

- It is hard to extend one report type without touching shared scheduling behavior.
- Failure handling cannot be improved cleanly while the model owns too many concerns.

Recommendation:

- Introduce report builder classes or registry functions.
- Keep the model focused on orchestration and persistence.

7. Portal roster flows are large and repetitive.

Evidence:

- [sports_federation_portal/controllers/rosters.py](sports_federation_portal/controllers/rosters.py) and [sports_federation_portal/models/federation_team_roster.py](sports_federation_portal/models/federation_team_roster.py) repeat scope loading, redirect handling, and action gating patterns.

Why it matters:

- Each UX change touches several repeated controller branches.
- This slows down maintenance and makes security review more tedious.

Recommendation:

- Split roster controllers by workflow segment.
- Factor redirect, scope lookup, and form error patterns into shared controller or service helpers.

8. Compliance target modelling is repeated across multiple models.

Evidence:

- [sports_federation_compliance/models/compliance_check.py](sports_federation_compliance/models/compliance_check.py), [sports_federation_compliance/models/document_submission.py](sports_federation_compliance/models/document_submission.py), and [sports_federation_compliance/models/document_requirement.py](sports_federation_compliance/models/document_requirement.py) all repeat target selections, target-field maps, and target-specific branching.

Why it matters:

- Adding a new target model requires synchronized edits in multiple places.
- Drift between these maps is an eventual bug source.

Recommendation:

- Extract one shared compliance target resolver or mixin.
- Make new target types extend that layer rather than editing each model independently.

9. Broad exception handling hides failure types and risks leaking internals.

Evidence:

- [sports_federation_notifications/models/notification_service.py](sports_federation_notifications/models/notification_service.py) catches broad exceptions and stores raw exception text in notification logs.
- [sports_federation_reporting/models/report_schedule.py](sports_federation_reporting/models/report_schedule.py) catches broad exceptions during report generation.
- Import wizards such as [sports_federation_import_tools/wizards/import_clubs_wizard.py](sports_federation_import_tools/wizards/import_clubs_wizard.py) convert arbitrary exceptions into row-level errors.

Why it matters:

- Operators receive inconsistent messages.
- Retryable infrastructure failures and developer defects are treated the same way.
- Raw exception text can disclose implementation details.

Recommendation:

- Use typed exceptions and categorized failure codes.
- Store sanitized operator messages while keeping full stack traces in server logs.

10. Migration discipline exists but is not systematic.

Evidence:

- Only one explicit migration script was found under [sports_federation_public_site/migrations/0.0.0/post-cleanup_website_menus.py](sports_federation_public_site/migrations/0.0.0/post-cleanup_website_menus.py).

Why it matters:

- Recent cross-module structural changes increase the chance of manual production repair steps.
- Upgrade confidence depends on consistent migration handling, not just fresh-install correctness.

Recommendation:

- Require migration impact review for model, view, and route ownership changes.
- Add per-module migration directories when upgrade behavior changes.

11. CI quality gates are useful but still narrow.

Evidence:

- [addons/.github/workflows/ci.yml](.github/workflows/ci.yml) limits Black and Flake8 runs through `BLACK_PATHS` and `FLAKE8_PATHS` environment lists.
- [addons/.flake8](.flake8) exists, and [addons/requirements.txt](requirements.txt) pins tooling, but only a subset of files is currently under lint automation.

Why it matters:

- Style drift and trivial lint defects can accumulate outside the allowlist.
- Developers get inconsistent quality feedback depending on which files they touched.

Recommendation:

- Expand lint coverage gradually to the whole repository.
- Start with a non-blocking repo-wide lint report, then gate after debt is reduced.

12. The repository has a documentation freshness problem for point-in-time reports.

Evidence:

- The previous `CODE_REVIEW_REPORT.md` and roadmap no longer matched the repository on CI, requirements, and test coverage.

Why it matters:

- Stale guidance slows triage and misleads contributors.
- This is a maintainability issue because engineers often trust reports before code.

Recommendation:

- Treat review and roadmap documents as dated artifacts.
- Archive them aggressively when superseded and add owner/date metadata.

### Low Severity And Readability Concerns

13. Many docstrings are mechanically descriptive rather than informative.

Evidence:

- Portal and compliance code contains many `Handle X flow` docstrings that restate the method name rather than the business rule or trust assumption.

Why it matters:

- It adds noise without helping the reader understand invariants or side effects.

Recommendation:

- Use docstrings mainly for assumptions, side effects, and failure semantics.

14. Presentation logic leaks into Python models.

Evidence:

- [sports_federation_portal/models/federation_tournament_registration.py](sports_federation_portal/models/federation_tournament_registration.py) builds excluded-team HTML in `_render_excluded_team_feedback_html()`.

Why it matters:

- Rendering logic is harder to test and reason about inside model code.
- It blurs the line between data preparation and UI generation.

Recommendation:

- Return structured data and let QWeb templates render the markup.

15. Cross-module workflow states are heavily string-driven.

Evidence:

- Literal values such as `draft`, `submitted`, `confirmed`, `expired`, and `closed` are repeated across multiple modules and helpers.

Why it matters:

- Refactors become grep-driven and therefore brittle.

Recommendation:

- Centralize frequently shared state semantics through helper predicates or shared enums where the semantics really are common.

## Maintainability And Readability By Subsystem

- Portal: good direction on service boundaries and tests, but still the largest concentration of repeated privileged flows and controller sprawl.
- Reporting: valuable operational coverage, but SQL and scheduling complexity are now structural concerns rather than style concerns.
- Compliance: strong functional coverage and good portal tests; internal target modelling is the main pain point.
- Import and Integrations: useful partner contract model and staging pipeline; security hardening is the top priority.
- Notifications: service abstraction is clear; exception handling and delivery semantics need stronger typing.
- Public Site: large public surface, but templates and controllers are reasonably organized and test-backed. The main concern is exposure management, not chaos.

## Recommended Near-Term Priorities

1. Harden integration credentials and upload boundaries.
2. Create a shared portal privilege boundary abstraction.
3. Split reporting monolith files and add report-specific invariants.
4. Simplify compliance target resolution.
5. Expand CI lint coverage and add documentation freshness checks.

## Roadmap Link

The replacement operating-period roadmap is in [ROADMAP.md](ROADMAP.md).
The prior roadmap has been archived in [ROADMAP_archive_2026-04-17.md](ROADMAP_archive_2026-04-17.md).

## Review Limits

- This was a static review. I did not run the full Odoo test matrix or perform load testing in this pass.
- Security observations focus on evident trust boundaries and exposure patterns, not a full adversarial assessment.
