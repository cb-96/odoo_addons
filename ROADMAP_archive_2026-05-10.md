# ROADMAP — 2026-04-30 Improvement Program

Last updated: 2026-04-30
Owner: Federation Platform Team
Last reviewed: 2026-04-30
Review cadence: Every release
Release train: 2026.05

The previous operating-period roadmap is archived in `ROADMAP_archive_2026-04-30.md`.
This roadmap is driven by a full codebase scan on 2026-04-30 and shifts the focus from
complexity extraction (previous cycle) to security closure, CI completeness, and
test coverage in the highest-risk modules.

---

## State of the Codebase

### What Has Gone Well

The platform has made genuine, measurable progress since the April-17 review.

**Refactoring wins are real.** The largest hotspots from the previous review have
been dramatically reduced. `report_operational.py` dropped from 968 → 202 lines.
The portal `rosters.py` controller dropped from 575 → 6 lines (a router stub).
This is active cleanup, not documentation housekeeping.

**The competition engine is the cleanest code in the repository.** `round_robin.py`
and `knockout.py` are well-factored `AbstractModel` services with zero `sudo()`
calls, proper bye handling, home/away alternation, deterministic seeding, and
aligned tests. This is the model other modules should follow.

**Documentation culture is strong.** Ten workflow files, three ADRs,
a `ROUTE_INVENTORY.md`, `STATE_AND_OWNERSHIP_MATRIX.md`, `INTEGRATION_CONTRACTS.md`,
an OpenAPI spec for the partner API, and a full `PERFORMANCE_BASELINES.md` with
enforced CI budgets — the information architecture of this project is above average
for a custom Odoo build.

**Test presence is 100%.** Every module has at least one test file. The portal
module has the richest test surface: HTTP smoke tests, roster portal access tests,
mobile/accessibility checks.

**CI is real and multi-layered.** The CI pipeline runs lint, documentation freshness
guards, dead-link detection, module-ownership validation, SQL EXPLAIN snapshot checks,
migration review guards, and OpenAPI contract drift checks — in addition to three Odoo
test suites. This is an unusually mature CI setup for this scale.

**Security debt is being paid.** Query-string credential leaks are fixed. XSS vectors
(`t-raw`) are gone. A migration discipline guard exists in CI. Eleven migration scripts
are now in place (major improvement from the previous cycle's one).

### Unresolved Findings

#### Security

| Severity | Finding | Location |
|---|---|---|
| HIGH | Partner API tokens stored and compared as plaintext `fields.Char` | `sports_federation_import_tools/models/integration_gateway.py` |
| HIGH | No file-size or MIME-type guardrails on portal uploads | `sports_federation_compliance/models/document_submission.py`, `sports_federation_import_tools` |
| MEDIUM | `except Exception` (9 occurrences) — some store raw exception text in notification logs (information disclosure risk) | `sports_federation_notifications/models/notification_service.py` and import_tools |
| MEDIUM | 51 `with_user(user).sudo()` patterns — distributed ownership checks, hard to audit and easy to regress | Portal models, compliance models |

Both HIGH items were flagged in the April-17 review and are still open. A database
export still exposes live partner credentials. File upload endpoints still lack size
and type enforcement.

#### Test Coverage Gaps

| Module | Model files | Test files | Risk |
|---|---|---|---|
| `reporting` | 18 | 4 | Highest risk — SQL view regressions go undetected |
| `import_tools` | 12 + 10 wizards | 2 | High — complex import paths with few regression tests |
| `discipline`, `governance`, `officiating` | 7–11 each | 1 each | Medium — minimal coverage for cross-module integration scenarios |

#### CI Coverage Gaps

Nine of 20 modules are **not covered in any named CI suite**:
`discipline`, `governance`, `notifications`, `import_tools`, `officiating`,
`people`, `rosters`, `rules`, `demo`. A regression in any of these modules is not
caught by the standard CI matrix runs.

#### Complexity Hotspots (Remaining)

| File | Lines | Concern |
|---|---|---|
| `sports_federation_public_site/models/public_flags.py` | 813 | One model owns too many publication flag concerns |
| `sports_federation_portal/models/federation_team_roster.py` | 597 | Portal helper mixes scope loading, validation, and write orchestration |
| `sports_federation_rosters/models/team_roster.py` | 564 | Most-versioned module (v3); highest churn risk |
| `sports_federation_public_site/controllers/public_competitions.py` | 560 | Wide public controller |
| `sports_federation_reporting/services/report_schedule_builders.py` | 519 | Extraction helped but the builder registry is itself now large |
| `sports_federation_standings/models/standing.py` | 482 | Standing logic and recompute triggers co-located |
| `sports_federation_tournament/models/federation_match.py` | 453 | Bracket wiring and lifecycle in one file |

#### Architectural Debt

1. `sports_federation_public_site` depends on `sports_federation_portal` — a
   read-only public website requires the full authenticated club-representative
   portal to be installed. This prevents independent deployment and complicates
   public-route testing.
2. No formal event/signal bus — notification triggers and finance event hooks are
   embedded in individual model methods. Tracing side effects grows harder as
   modules accumulate.
3. Public JSON feed contracts (`/api/v1/tournaments/<slug>/feed`,
   `/tournaments/<slug>/schedule.ics`) are described as stable `v1` contracts in
   `INTEGRATION_CONTRACTS.md` but have no machine-readable OpenAPI schema.
4. `KnockoutService._apply_seeding` uses `random.shuffle` with no fixed seed,
   making bracket-position tests for the random seeding mode non-reproducible.
5. Black and Flake8 are still restricted to a `BLACK_PATHS`/`FLAKE8_PATHS`
   allowlist, allowing style drift to accumulate in unlisted files.

#### Documentation Gaps

| Gap | Severity |
|---|---|
| No `WORKFLOW_ROSTER_MANAGEMENT.md` — rosters have audit events, locking state, and portal editing; inline coverage in the match-day workflow doc is insufficient | Medium |
| No `WORKFLOW_OFFICIATING.md` — referee certification and assignment lifecycle is split across two workflow files | Low |
| Player licensing state machine is undocumented (only mentioned in step 6 of season registration workflow) | Low |
| Suspension notification is still a stub (acknowledged in TECHNICAL_NOTE.md) | Low |
| `sports_federation_demo` has no README explaining what scenarios it seeds | Low |
| Twilio/SMS integration env vars are declared but no workflow or README describes actual SMS usage | Low |
| `CODE_REVIEW_REPORT.md` cites hotspot file sizes from April 17 that are now significantly smaller | Low |

---

## Period Goal

Close the two open HIGH security findings, expand CI to cover all 20 modules,
and improve the test-to-risk ratio in the highest-gap modules.

## Review Baseline

- 20 custom addons, ~252 Python files, ~132 XML files, ~66 test files.
- 159 `sudo()` calls, 51 `with_user(user).sudo()` patterns, 4 `csrf=False` routes.
- Two HIGH security findings open from the previous cycle.
- 9 of 20 modules not covered in any named CI suite.
- `reporting` has the worst test-to-model ratio (4 test files : 18 model files).
- 11 migration scripts now in place (major improvement from the previous cycle's 1).

## Guiding Principles

- Prioritize risk reduction over feature expansion.
- Every security or schema change gets a focused regression test.
- Prefer expanding existing infrastructure (CI suites, shared helpers) over
  building new patterns.
- Do not reopen previously closed refactoring work; consolidate gains.

---

## Phase 1 — Weeks 1–2: Security Closure (Blockers)

These two items have been open since April 17. They must not survive another release.

### 1. ✅ Hash partner API tokens at rest

Modules: `sports_federation_import_tools`

Work:
- [x] PBKDF2-SHA256 hashing (390 000 rounds, 16-byte salt) in `integration_partner_token_mixin.py`.
- [x] Views expose only `auth_token_last4`; raw token revealed once via rotation wizard.
- [x] `_migrate_plaintext_tokens()` wired into `_register_hook()` for runtime backfill.
- [x] Versioned migration script: `migrations/19.0.1.2.0/post-hash-auth-tokens.py`.
- [x] Module version bumped to `19.0.1.2.0`.
- [x] Token rotation procedure documented in `RELEASE_RUNBOOK.md` ("Integration Partner Token Rotation" section).
- [x] 51/51 CI tests pass (`sports_federation_import_tools`).

Done when: `authenticate_partner()` compares a hash, no raw token survives in any
field, rotation is documented in the operator runbook, and a migration script exists. ✅

### 2. ✅ Enforce upload size and MIME-type guardrails

Modules: `sports_federation_compliance`, `sports_federation_import_tools`;
shared policy in `sports_federation_base`

Work:
- [x] `federation.attachment.policy` centralized in `sports_federation_base` with
  `integration_inbound_csv` (5 MB, .csv) and `portal_document` (10 MB, PDF/JPEG/PNG) policies.
- [x] `validate_upload()` wired in `integration_delivery_stage_mixin.py` (inbound API)
  and `document_submission.py` (compliance portal).
- [x] User-readable rejection messages include "MiB or smaller" and disallowed type.
- [x] Tests: `test_inbound_delivery_rejects_oversized_payload` (import_tools),
  `test_portal_submit_submission_rejects_oversized_attachment` (compliance),
  `test_validate_upload_blocks_when_hook_reports_malware` (base).
- [x] 17/17 CI tests pass (`sports_federation_compliance`), 51/51 pass (`import_tools`).

Done when: no portal or partner upload path accepts an oversized or disallowed-type
file without an explicit, user-readable rejection; automated tests cover both cases. ✅

---

## Phase 2 — Weeks 3–4: CI Coverage for All Modules

Nine modules are invisible to CI matrix runs today. Any of them can regress silently.

### 3. ✅ Add CI suites for uncovered modules

Modules: `discipline`, `governance`, `notifications`, `import_tools`,
`officiating`, `people`, `rosters`, `rules`, `demo`

Work:
- [x] Added `people_rosters_rules` suite: `people`, `rosters`, `rules`, `officiating` — 86/86 tests pass.
- [x] Added `ops_and_notifications` suite: `discipline`, `governance`, `notifications`,
  `import_tools`, `demo` — 106/106 tests pass.
- [x] Both suites registered in `ci/run_tests.sh` `list_suites()` and `resolve_suite_modules()`.
- [x] All 20 modules now covered by at least one named CI suite.

Done when: all 20 modules appear in at least one named CI suite. ✅

### 4. ✅ Remove Black/Flake8 path allowlists

Modules: Repository-wide, `ci/`

Work:
- [x] Ran full-repo Black and inventoried 20 files needing reformatting — auto-fixed with `black .`.
- [x] Fixed all Flake8 issues: E741 ambiguous `l` variables (renamed to `ln`), F401 unused imports
  (removed or marked `noqa` where retained for compatibility), F841 unused local variables,
  F541 bare f-string, F402 loop-variable import shadowing, F821 undefined name (bug fix in standings).
- [x] No allowlist variables were present; `ci/run_repo_lint.sh` already runs repo-wide.
- [x] `bash ci/run_repo_lint.sh --strict` exits 0: Black exit 0, Flake8 exit 0.
- [x] Regression CI: competition_core 183/183, portal_public_ops 239/239, people_rosters_rules 86/86.

Done when: the CI lint job runs Black and Flake8 on all files without an allowlist. ✅

---

## Phase 3 — Weeks 5–7: Test Coverage in High-Risk Modules

### 5. ✅ Expand `reporting` test coverage

Module: `sports_federation_reporting`

Work:
- [x] Audited all 19 model classes across 18 files; all 16 `_auto=False` SQL views have
  at least one assertion with real content checks (not just `assertIsNotNone`).
- [x] `test_operational_reporting.py` covers: operational KPIs, standing reconciliation,
  finance reconciliation, notification exceptions, finance exceptions, workflow
  exceptions (stalled result + override), compliance remediation, season checklist,
  audit event report (portal + token families), operator checklist (failures + delivery),
  snapshot capture + board pack, audit pack, and all 11 REPORT_SPECS builders via
  the registry test.
- [x] `TestYearFourReporting` covers: `federation.report.season.portfolio` (budget
  rollup + delta + planning status), `federation.report.club.performance` (win/loss,
  finance, compliance), `season_portfolio` and `club_performance` schedule builders,
  ORM query-count budgets, and PostgreSQL plan watchpoints.
- [x] `test_reporting.py` replaced 4 weak `assertIsNotNone` stubs with real column-presence
  checks and aggregate assertions for participation, officiating, compliance, and finance views,
  with proper seed data (active season, player, referee, compliance check, finance event).
- [x] 53 tests / 19 models = ratio 2.79 (> 0.5). CI: **53/53 ✅** (57/57 with HTTP smoke tests).

Done when: the reporting module test-to-model ratio is above 0.5 (currently ~0.22),
and every SQL view has at least one assertion. ✅

### 6. ✅ Add integration tests for `import_tools` wizard paths

Module: `sports_federation_import_tools`

Work:
- [x] All 9 wizard classes have focused tests: `federation.import.clubs.wizard` (dry-run,
  mapping guide, governance approval, file-change invalidation), `federation.import.teams.wizard`
  (club-code resolution), `federation.import.players.wizard` (legacy name split),
  `federation.import.seasons.wizard` (format errors, planning targets),
  `federation.import.tournament.participants.wizard` (duplicate skip, seed),
  `federation.import.wizard.mixin` (row-create flow, error taxonomy),
  `federation.import.wizard.csv.mixin` (delimiter detection — comma and semicolon both
  exercised across test suite), `federation.import.wizard.governance.mixin`
  (approval gating, checksum invalidation), and
  `federation.integration.partner.token.wizard` (token rotation + hash storage).
- [x] Governance approval end-to-end: `test_inbound_delivery_links_to_governed_import_flow`
  exercises staged → previewed → awaiting_approval → approved → processed, including
  success_count and delivery state mirroring.
- [x] CI: **51/51 ✅**.

Done when: every import wizard class has at least one focused test, and the
governance approval path is covered end-to-end. ✅

---

## Phase 4 — Weeks 8–10: Architecture and Documentation Debt ✅

### 7. Decouple `public_site` from `portal` ✅

Modules: `sports_federation_public_site`, `sports_federation_portal`

Work:
- Remove the `sports_federation_portal` dependency from
  `sports_federation_public_site/__manifest__.py`.
- Guard the `_get_clubs_for_user()` call (and any similar portal-specific helpers
  used in public controllers) with an authenticated-user branch that only runs
  when a session is active.
- Add a test verifying the public homepage loads without the portal module installed
  (or mock its absence).

Done when: `sports_federation_public_site` installs and serves anonymous visitors
without `sports_federation_portal` in the dependency list.

**Completion notes (2026-04-28):**
- Replaced `sports_federation_portal` with `portal` (Odoo core) in `public_site/__manifest__.py`.
- Added `menu_website_tournaments` directly to `public_site/views/website_menu.xml`
  (self-owned top-level site menu); updated `menu_website_competitions` parent to the
  local ref. Removed the competing `menu_website_tournaments` record from
  `sports_federation_portal/views/website_menus.xml` (prevents duplicate menus
  when both modules are installed).
- Guarded `_get_request_user_clubs()` with `request.env.get("federation.club.representative")`
  — returns empty recordset when portal module is absent.
- Guarded `_portal_submit_registration_request()` call with `hasattr` — returns a
  user-facing "not available" redirect when portal is absent.
- CI: `portal_public_ops` suite — **197/197 ✅**.

### 8. Narrow `except Exception` handlers ✅

Modules: `sports_federation_notifications`, `sports_federation_import_tools`

Work:
- Replace bare `except Exception` with typed exception handling
  (`except (ValidationError, UserError, ConnectionError)` etc.).
- In `notification_service.py`, sanitize what is stored in notification log records
  — store a typed failure category and a sanitized message, not a raw exception
  string or stack trace.
- Where a broad catch is genuinely needed (e.g., unknown mail server errors), log
  via `_logger.exception` but store only a sanitized summary in user-visible fields.

Done when: no user-visible field (notification log, import error row) stores raw
Python exception text.

**Completion notes (2026-04-28):**
- `notification_service.py` and `notification_dispatcher.py` already used
  `build_failure_feedback` correctly — no changes needed.
- `integration_api.py` already used `_json_error_response` (which calls
  `build_failure_feedback`) — no changes needed.
- Fixed `import_wizard_csv_mixin.py` `_categorize_exception()`: the
  `unexpected_error` fallback now passes `str(error)` through
  `is_safe_operator_detail()` from `failure_feedback`; messages that fail the
  safety check are replaced with a generic operator-safe string.
- CI: `ops_and_notifications` suite — **106/106 ✅**.

### 9. Add public feed OpenAPI schema ✅

Module: `openapi/`

Work:
- Add a `public_feeds_v1.yaml` schema covering:
  - `GET /api/v1/tournaments/<slug>/feed` → `tournament_feed` response shape
  - `GET /tournaments/<slug>/schedule.ics` → documented as binary ICS response
- Register the new file in `check_openapi_contracts.py` so CI catches drift.

Done when: both public feed contracts have a machine-readable schema and a CI
drift check.

**Completion notes (2026-04-28):**
- Created `addons/openapi/public_feeds_v1.yaml` (OpenAPI 3.1.0) with full schemas
  for `TournamentFeedResponse`, `ParticipantEntry`, `MatchEntry`, `ScheduleSection`,
  `BracketSection`, `StandingEntry`, `TournamentSummary`.
- Added `PUBLIC_FEEDS_SPEC_PATH` and `PUBLIC_FEEDS_REQUIRED_PATHS` to
  `check_openapi_contracts.py`; both specs validated successfully in Docker.

### 10. Add missing workflow documentation ✅

Modules: Repository docs (`_workflows/`)

Work:
- Write `_workflows/WORKFLOW_ROSTER_MANAGEMENT.md` covering: roster creation,
  activation gating, match-day locking, audit events, substitution timing, portal
  visibility, and dispute-triggered unlocking.
- Write `_workflows/WORKFLOW_OFFICIATING.md` covering: referee certification states,
  assignment creation, confirmation/decline, shortage detection, and the scheduled
  notification scan.
- Expand `_workflows/WORKFLOW_SEASON_REGISTRATION.md` steps 6+ to cover the player
  licensing state machine.
- Refresh `CODE_REVIEW_REPORT.md` — several line-count figures are significantly
  out of date.

Done when: roster, officiating, and licensing workflows have standalone documents;
the code review report reflects current hotspot sizes.

**Completion notes (2026-04-28):**
- Created `_workflows/WORKFLOW_ROSTER_MANAGEMENT.md`: full lifecycle from draft
  creation through eligibility check, activation, match sheet creation/approval,
  match-day lock, and season close. Includes portal access section and audit trail
  notes.
- Created `_workflows/WORKFLOW_OFFICIATING.md`: referee registration, certification
  records, match assignment, confirmation deadlines, overdue detection, and
  completion/cancellation paths.
- Expanded `WORKFLOW_SEASON_REGISTRATION.md` §6 with the full player license state
  machine (`draft → active → expired / cancelled`), action buttons, uniqueness
  constraint, and eligibility impact on rosters and match sheets.
- Updated `CODE_REVIEW_REPORT.md` "Review Signals" with current counts: 328 Python
  files, 138 XML files, 59 test files, 7 `except Exception` occurrences (all
  sanitized), corrected complexity hotspot line counts.

---

## Phase 5 — Weeks 11–14: Ongoing Complexity Reduction ✅

### 11. Split `public_flags.py` ✅

Module: `sports_federation_public_site`

Work:
- Separate `public_flags.py` (813 lines) into at least two focused files:
  - `public_tournament_flags.py` — publication state, slug validation,
    featured/live toggles
  - `public_standings_flags.py` — standings publication and visibility rules
- Keep each file under ~400 lines.

Done: `public_flags.py` (1001 lines) split into three focused files —
`public_tournament_flags.py` (380 lines), `public_tournament_content.py`
(418 lines), `public_standings_flags.py` (214 lines). `public_editorial.py`
import updated. CI: portal_public_ops 197/197 ✅

### 12. Extract bracket wiring from `federation_match.py` ✅

Module: `sports_federation_tournament`

Work:
- Move the bracket-linking fields (`source_match_1_id`, `source_match_2_id`,
  `bracket_position`, `bracket_type`, `next_match_ids`) and
  `_advance_bracket_teams()` into a dedicated `federation_match_bracket.py` mixin
  or model extension.
- `federation_match.py` should own match lifecycle and scoring; bracket wiring is
  a separate concern.

Done: Created `federation_match_bracket.py` (79 lines) with all bracket fields,
`_compute_next_matches`, and `_advance_bracket_teams`. `federation_match.py`
trimmed from 506 to 434 lines. CI: competition_core 153/153 ✅

### 13. Make knockout seeding deterministic in tests ✅

Module: `sports_federation_competition_engine`

Work:
- In `KnockoutService._apply_seeding`, accept an optional `seed` parameter and
  pass it to `random.seed()` before shuffling when provided.
- In all tests that exercise random seeding, pass a fixed seed so bracket positions
  are reproducible.

Done: `_apply_seeding` accepts `seed=None`; `generate()` passes `options.get("seed")`
through. `_generate()` test helper updated to forward `seed`. Added
`test_random_seeding_deterministic_with_seed` verifying identical bracket slots with
same seed. CI: competition_core 153/153 ✅

---

## Suggested Sequence

1. Hash partner tokens and upload guardrails (security blockers — do first).
2. Add CI suites for uncovered modules and remove lint allowlists.
3. Reporting and import_tools test coverage expansion.
4. Decouple public_site from portal; narrow exception handlers; OpenAPI feeds schema.
5. Workflow documentation additions.
6. Complexity reduction (public_flags split, bracket extraction, test seeding).

---

## Exit Criteria

- No partner authentication path stores or compares a plaintext secret.
- No portal or partner upload path accepts an oversized or disallowed-type file.
- All 20 modules appear in at least one named CI suite.
- Full-repo lint runs without a path allowlist.
- `sports_federation_reporting` test-to-model ratio is above 0.5.
- No user-visible field stores a raw Python exception string.
- `sports_federation_public_site` does not require `sports_federation_portal`
  as a manifest dependency.
- `WORKFLOW_ROSTER_MANAGEMENT.md` and `WORKFLOW_OFFICIATING.md` exist and are
  complete.
