# ROADMAP — 2026-05-10 Improvement Program

Last updated: 2026-05-10
Owner: Federation Platform Team
Last reviewed: 2026-05-10
Review cadence: Every release
Release train: 2026.06

The previous operating-period roadmap is archived in `ROADMAP_archive_2026-05-10.md`.
This roadmap is driven by a full codebase scan on 2026-05-10. All 13 items from the
2026-04-30 cycle are closed. This cycle focuses on the residual security surface in
portal access control, data model correctness in the rosters module, performance in
standings computation, and UX polish.

---

## State of the Codebase

### What Has Gone Well (2026-04-30 → 2026-05-10)

**All 13 items from the previous roadmap are closed.** The April-30 cycle delivered:
security closure (token hashing, upload guardrails, exception sanitization), full CI
coverage for all 20 modules, a clean lint baseline (Black + Flake8 repo-wide with no
allowlists), expanded test coverage in `reporting` (ratio now 2.79) and `import_tools`
(all 9 wizard classes covered), public site decoupled from the portal module, two new
workflow docs (`WORKFLOW_ROSTER_MANAGEMENT.md`, `WORKFLOW_OFFICIATING.md`), and
complexity reduction across `public_flags.py`, `federation_match.py`, and the knockout
seeding path.

**12 CI tour tests (T-01 through T-12) are all passing.** A complete end-to-end
integration test exists for every major workflow in the platform.

**The platform is in the best shape it has ever been.** Remaining findings are
medium-to-low severity with no blocking security issues from the previous cycle.

### Unresolved Findings

#### Security

| Severity | Finding | Location |
|---|---|---|
| HIGH | 51 `with_user().sudo()` calls with no centralized ownership check — one missed assertion is a silent breach | Portal models, compliance models |
| HIGH | Roster detail routes fetch via `.sudo()` without verifying the requesting user represents the roster's club | `sports_federation_portal/controllers/roster_portal.py:108` |

Both findings are residual from the April-17 review. The number of distributed
`sudo()` patterns has grown slightly with portal expansion and is now harder to audit.

#### Data Model Correctness

| Severity | Finding | Location |
|---|---|---|
| MEDIUM | Roster unique constraint is `UNIQUE(team_id, season_id, competition_id, name)` — because `name` is auto-generated, two rosters for the same scope can bypass it with different names | `sports_federation_rosters/models/team_roster.py:140` |
| MEDIUM | Roster name generation uses a search-then-insert loop — two concurrent creates can both pass the loop and collide at DB insert | `sports_federation_rosters/models/team_roster.py:236` |

#### Performance

| Severity | Finding | Location |
|---|---|---|
| MEDIUM | `_build_standing_table()` filters participants with `recordset.filtered(lambda p: ...)` inside a match loop — O(n × m) for n matches × m participants | `sports_federation_standings/models/standing.py:193` |
| MEDIUM | `ready_for_submission` (match sheet) and `ready_for_activation` (roster) are computed but not stored — domain filters on them trigger full recompute | `sports_federation_rosters/models/` |

#### Documentation and UX

| Severity | Finding | Location |
|---|---|---|
| LOW | Standings README references field names `position` and `matches_played`; model uses `rank` and `played` | `sports_federation_standings/README.md` |
| LOW | `min_players_required`, `max_players_allowed` (roster) and `rule_set_id` (standing) have no `help=` text — ambiguous per-match vs. per-season semantics | `sports_federation_rosters`, `sports_federation_standings` |

---

## Period Goal

Close the two residual HIGH security findings in portal access control, fix the
rosters data model correctness issues, eliminate the O(n²) standings hotspot, and
make readiness computed fields storable and filterable.

## Review Baseline

- 20 custom addons, ~328 Python files, ~138 XML files, ~66 test files.
- 0 HIGH security findings from upload/token vectors (closed in previous cycle).
- 2 HIGH security findings open: portal `sudo()` audit surface and missing club-ownership check on roster routes.
- 51 `with_user().sudo()` calls spread across portal and compliance models.
- `team_roster` unique constraint does not enforce one-roster-per-scope semantics.
- Standings `_build_standing_table()` is O(n × m); acceptable now but degrades at scale.

## Guiding Principles

- Security findings close before any other work ships.
- Every constraint fix gets a migration script and a regression test.
- Prefer stored computed fields over repeated recompute for fields used in domain
  filters or list views.
- Do not reopen previously closed complexity work.

---

## Phase 1 — Weeks 1–2: Security Closure ✅ DONE (2026-05-10)

### 1. Centralize portal sudo() ownership checks ✅

Modules: `sports_federation_portal`

**Problem:** Portal `with_user(user).sudo()` calls lacked a single auditable
ownership checkpoint. Any new portal method that calls `.sudo()` without a
scope check was a silent data-leak risk.

**Implemented:**
- Added `_assert_portal_owns(records, scope_domain, user)` convenience wrapper on
  `federation.portal.privilege` (delegates to the existing `portal_assert_in_domain`
  with a consistent default access-denied message).
- Added `ci/check_portal_sudo_guard.py` — a grep-based CI guard that fails if any
  `.sudo()` in portal controllers lacks an adjacent ownership scope indicator (a
  `_portal_*` method call, `clubs.ids`, `club_id`/`team_id` domain filter, etc.)
  within a ±15-line window. Guard passes on the current codebase with 0 violations.
- Added `tests/test_portal_ownership_guard.py` (9 tests) — proves `AccessError` is
  raised for cross-club ID guessing and that the deny-all domain fires for users with
  no representative link.

### 2. Fix roster detail route ownership check ✅

Module: `sports_federation_portal`

**Already implemented** (discovered during audit): `_get_portal_roster()` in
`roster_helpers.py` already routes through `portal_search_by_id()` with a
`_portal_get_scope_domain(user)` scope filter (team_id/club_id). Guessing another
club's roster ID returns an empty recordset → HTTP 404. Record rules at DB level
(`rule_team_roster_portal_own`) provide a second enforcement layer.

**Tests already in place:** `test_roster_portal_access.py` covers cross-club
isolation for rosters, match sheets, and audit events.

---

## Phase 2 — Weeks 3–4: Data Model Correctness ✅ DONE

### 3. Fix team roster uniqueness constraint ✅

Module: `sports_federation_rosters`

**Problem:** The DB constraint `UNIQUE(team_id, season_id, competition_id, name)` is
ineffective because `name` is auto-generated per scope. Two rosters for the same
`(team_id, season_id, competition_id)` can coexist with different auto-generated
names, violating the intended one-roster-per-scope rule.

**Resolution (v19.0.1.5.0):** The name-based constraint is incorrect business logic —
multiple draft/closed rosters per scope are valid (e.g. the "close old, create new"
workflow). The constraint was simply dropped. One-active-roster-per-scope continues to
be enforced by the partial DB indexes added in 19.0.1.4.0 and `_assert_unique_active_roster()`.

Work:
- [x] Dropped UNIQUE(team_id, season_id, competition_id, name) constraint via migration 19.0.1.5.0.
- [x] Confirmed active-roster uniqueness is enforced by existing 19.0.1.4.0 partial indexes.
- [x] Bumped module version to 19.0.1.5.0.
- [x] Tests: verify multiple draft rosters per scope are allowed; activating a second raises ValidationError.

Done when: CI passes. **CI passed: 69/69 tests, 0 failures.**

### 4. Fix roster name generation race condition ✅

Module: `sports_federation_rosters`

**Problem:** `_generate_unique_name()` in `team_roster.py` uses a
while-`search_count` loop followed by an insert. Two concurrent creates can both
pass the while check and then collide at the DB unique constraint.

**Resolution (v19.0.1.5.0):** Removed the while-`search_count` loop from
`_get_generated_name`. The name is now built directly from the base pattern.
Multiple rosters may share the same auto-generated name, which is acceptable
since name is no longer a uniqueness key.

Work:
- [x] Removed the search-count loop from `_get_generated_name()`.
- [x] Name is now the base pattern directly (team + season/competition).
- [x] Tests: verify base pattern is used with no " (2)" suffix.

Done when: race condition eliminated; no collision-avoidance loop. **Done.**

---

## Phase 3 — Weeks 5–6: Performance ✅ DONE

### 5. Fix standings O(n²) participant lookup ✅

Module: `sports_federation_standings`

**Problem:** `_build_standing_table()` called `participants.filtered(lambda p: p.team_id == match.home_team_id)` inside a loop over all matches — O(n × m).

**Resolution:** Replaced with a pre-built `participant_map = {p.team_id.id: p for p in participants}` dict before the match loop. Lookups inside the loop are now O(1). No additional DB queries as match count grows.

Work:
- [x] Replaced `filtered(lambda ...)` inside match loop with `participant_map.get(...)`.
- [x] Added performance regression test `test_standings_performance.py`: 200 matches, 10 participants, asserts `_build_standing_table()` issues ≤ 10 queries.

Done when: O(n+m); query count ≤ 10 for 200-match test. **CI passed: 29/29 tests.**

### 6. Make readiness fields stored computed ✅

Module: `sports_federation_rosters`

**Status:** Already implemented — `ready_for_activation` (roster) and
`ready_for_submission` (match sheet) both have `store=True` with correct
`@api.depends(...)` triggers. DB columns confirmed present. No further work needed.

---

## Phase 4 — Weeks 7–8: Documentation and UX Polish ✅ DONE

### 7. Fix standings documentation field name mismatch ✅

Module: `sports_federation_standings`

**Problem:** `sports_federation_standings/README.md` referenced `position`, `matches_played`,
`wins`/`draws`/`losses`, `goals_for`/`goals_against`/`goal_difference`, and `notes` — none of which
exist on the model. Actual fields are `rank`, `played`, `won`/`drawn`/`lost`,
`score_for`/`score_against`/`score_diff`, `note`, and `tiebreak_notes`.

Work:
- [x] Updated `README.md` standing-line field list to match actual model field names.
- [x] Searched `_workflows/` and `TECHNICAL_NOTE.md` — no stale field names found there.

Done when: docs and model field names match exactly. **Done.**

### 8. Add help= text to ambiguous fields ✅

Modules: `sports_federation_rosters`, `sports_federation_standings`,
`sports_federation_compliance`

Work:
- [x] `min_players_required` / `max_players_allowed` — added `help=` clarifying these are
  season/competition **squad registration** caps (not per-match selection limits) that
  override the rule-set defaults; label unchanged (already clear enough in context).
- [x] `rule_set_id` on `federation.standing` — added `help=` explaining the inheritance chain
  (stage → tournament → competition) and when to set it explicitly.
- [x] `validity_days` on compliance `document.requirement` — improved `help=` to clarify this
  is a **hard expiry window** (no grace period) used to compute `expiry_date` when not
  set manually.

Done when: all three field groups have unambiguous `help=` text. **CI passed: 134/134 tests.**

---

## Suggested Sequence

1. Items 1 and 2 (security — block the next release if not done).
2. Items 3 and 4 (data model — constraint fix and race condition; migration needed).
3. Items 5 and 6 (performance — independent of each other, can run in parallel).
4. Items 7 and 8 (docs and UX — low-risk, fill any spare capacity).

---

## Exit Criteria

- All portal `with_user().sudo()` calls flow through a single `_assert_portal_owns()`
  guard; CI enforces the pattern on new code.
- Accessing another club's roster URL via a guessed ID returns HTTP 403; automated
  test proves it.
- DB constraint enforces one roster per `(team, season, competition)` regardless of
  auto-generated name.
- Concurrent roster creation for the same scope results in exactly one committed
  record and one clean `ValidationError`.
- `_build_standing_table()` uses dict lookup; query count in a 200-match test is < 10.
- `ready_for_submission` and `ready_for_activation` are stored; filtered list views
  do not trigger per-row recompute.
- Standings README field names match the model (`rank`, `played`).
- `min_players_required`, `rule_set_id` (standings), and `validity_days` all have
  `help=` text.
