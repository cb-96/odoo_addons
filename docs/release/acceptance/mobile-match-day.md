# Mobile match-day acceptance

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

Acceptance scenarios for mobile court score capture, interruption recovery and
the mobile official and manager pages in `sports_federation_live_workspace`.
Court commands, result review, duty coverage and replacement reuse their
existing workflows: there is no parallel score database, result-approval
bypass or automatic score merge.

## Behaviour under test


- `/my/matchday-mobile` links assigned courts, current individual official assignments and manager coverage/attendance actions.
- One assigned court opens automatically. The last authorised court and match are remembered by database and account on the device. The current unfinished match is selected when no previous match is chosen.
- Court score entry leads with teams, court, venue and save status. Match queue, lineups and exception controls can be expanded without crowding the score controls.
- Save states explicitly distinguish device-only edits, queued submission with unknown server outcome, synchronised draft, submitted, verified, approved and contested results.
- Device-save status is displayed only after a journal write and readback succeed. Storage failure says not saved and blocks sending a newly queued command until persistence succeeds.
- Pending commands retain original keys, revisions, payloads and signatures across reload and retry. The server returns acknowledged keys; the client clears only a fully acknowledged batch.
- Later unsent edits are retained when an earlier queued batch synchronises. Changed context requires explicit reconciliation.
- A failed match-queue refresh cannot reverse or mislabel a confirmed result acknowledgement.
- Check server result status refreshes authoritative state, including approval, without another submission.
- Corrupt journals are not silently replaced. Concurrent tabs are excluded with Web Locks, compare-before-write checks and storage-change detection.
- Recovery exports evidence before an explicit server reload. The old journal is not replaced until the authoritative read succeeds. Governed context acknowledgement requires a reason and no unsaved edits.
- Operational deviations show the existing recorded type and reason, separately from the published schedule.
- Numeric controls have distinct accessible names, integer steps, mobile input modes and keyboard-visible focus. Court controls wrap at narrow widths.
- Officials retain existing acceptance/decline actions and see the venue address and court. Request check-in records a signed, idempotent request only. Manager-confirmed attendance remains a separate existing action.
- Managers can confirm attendance and replace an unavailable official from mobile forms. Replacement reuses the existing locked resolution wizard, its preview signature, history and eligibility checks. Repeated submission of the same applied preview does not create another successor; different replay details are rejected.
- Submitted/approved score correction links to the canonical governed result record. Permissions and independent review still apply.

## Important boundaries


**No cold-start offline PWA is claimed.** An already loaded authenticated court can capture scores during connectivity loss. Reloading the entire application shell while fully offline is not guaranteed: reconnect to load the application and current court access, then recover the durable journal. If the match is moved to another court, access is revoked or the session closes, commands stop and evidence must be reconciled by the authorised organiser.

Court editing requires a secure browser supporting Web Locks. Unsupported browsers fail closed with a fallback message instead of risking concurrent-tab overwrite. Use HTTPS in staging/production. Validate the actual mobile browsers before rollout.

Local score journals are device data, not official results. They exclude cached player lineups. Recovery exports exclude the in-memory lineup list, but existing legacy raw journals may contain earlier cached fields. Treat exports as operational evidence and follow your retention/access policy. Clearing browser storage, private-mode expiry, device loss or deliberate deletion is outside the acknowledged-save interruption guarantee. No arbitrary automatic expiry is added to unresolved evidence.

A check-in request is not proof of physical attendance. The organiser confirms attendance separately. Existing acceptance and eligibility requirements are not relaxed. Replacement starts unaccepted.

## Automated validation


Source-level checks and policy tests:

```bash
PYTHONDONTWRITEBYTECODE=1 python ci/static_checks.py
PYTHONDONTWRITEBYTECODE=1 python ci/test_live_workspace_policy.py
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s ci -p test_duty_coverage_policy.py
node ci/test_mobile_recovery.mjs
node --check ci/mobile_matchday_browser.mjs
node --check sports_federation_live_workspace/static/src/workspaces.js
```

Runtime tests are tagged `sf_mobile_matchday`; court and browser tests are tagged `sf_live_workspace`.

```bash
odoo-bin -d STAGING_TEST_DB -u sports_federation_live_workspace \
  --test-enable --test-tags sf_mobile_matchday,sf_live_workspace,sf_duty_coverage \
  --stop-after-init
```

Run fresh installation and upgrade tests too. Test independent transactions for result/context races, not just sequential ORM calls. XML parsing does not establish QWeb or Owl runtime validity.

The live browser runner requires the installed Playwright package and Chromium, a staging mail sink, an HTTPS/secure origin and disposable fixtures:

```bash
node ci/mobile_matchday_browser.mjs
```

Set `SF_BASE_URL` and `SF_MOBILE_FIXTURES` through your test environment/secret store. Do not commit credentials. The JSON configuration has:

- `operator`, `official`, `manager`: each contains `login` and `password`.
- `scenarios`: entries for `before_submission`, `during_submission`, `after_submission`, `duplicate_replay`, `reload_reconnect`, `changed_context`, `second_tab`, `storage_failure`.
- Each scenario has `matchday_id`, `court_id`, `match_id`, and optionally `court_index`. Use a fresh runnable aggregate-score match for every scenario.
- `official_accept_venue`: `assignment_id`, initially unaccepted and eligible.
- `organiser_replace`: `assignment_id`, `referee_id`, an eligible available successor.

The runner uses 360×800 viewports, keyboard score entry and keyboard official/replacement actions. It drops requests or responses, checks durable original keys, reconnects, compares receipt counts, tests another-session edits, storage failure and second-tab exclusion. Missing fixtures are blocked, never counted as passes. Its report is not human usability evidence.

## Defined interruption suite


Run all scenarios against the same candidate and preserve receipts, audit history and exported evidence. Compare the canonical score, capture revision, original operation keys and receipt counts before/after.

1. **Before submission:** disconnect before clicking submit. A queued device submission must not be described as submitted on the server. Reconnect and synchronise once.
2. **During submission:** abort the request before a response. Retain the exact command. Retry with the same key and payload. No lost acknowledged save or duplicate submission.
3. **After submission:** allow the server to commit, then discard its response. The device still shows outcome unconfirmed. Replay the original key; the server returns its receipt without repeating submission.
4. **Reload/reconnect:** persist a queued draft, reload with connectivity restored, reopen the remembered match and synchronise. Recover exact scores and original keys.
5. **Changed context:** another authenticated session changes the draft, published slot, result or court context. Preserve local edits, show a conflict and never overwrite silently. A moved court may deny access rather than allow local reconciliation.
6. **Duplicate replay:** repeat a committed save/submission with the same key. One immutable receipt and one business transition. Reuse of a key with different payload/actor must be rejected.
7. **Storage failure:** force a quota/write/readback failure. Do not claim saved on device; do not send a newly queued command without a verified durable write. Keep the screen open and export evidence.
8. **Second tab:** open the same database/user/court/match in another tab. It must not edit the first tab's journal. Test lease release after the first tab closes and storage-change conflict handling.

Also test closed sessions, revoked court access, stale official acceptance/check-in signatures, changed replacement preview, malformed journals, interrupted/disputed outcomes, intended 0–0, period totals and approved-result immutability.

## Human usability tests


Use ordinary role accounts and realistic fixtures. Give goals, not navigation instructions. Record every assisted or failed attempt.

- **Official:** open the mobile entry, accept the assignment, find the venue/address/court and request check-in. Explain why attendance is still unconfirmed until the organiser confirms it.
- **Court operator:** open the assigned current match, enter a simple aggregate result, save, submit and check server state. Explain where the result is stored at each step.
- **Recovery:** experience each interruption boundary, reload/reconnect, verify the exact outcome and avoid a new submission when the original key is pending.
- **Changed session:** identify the conflict, export evidence and perform the permitted explicit recovery. No automatic score merging.
- **Organiser:** identify unavailable coverage, record a reasoned replacement, verify retained predecessor history and successor acceptance requirements, then confirm attendance separately.

Repeat critical actions at 360 CSS pixels and with keyboard only. Check visible focus, field labels, error focus, modal confirmation, expandable details, no hidden essential actions and no horizontal page overflow. The numeric score controls are not a substitute for screen-reader testing.

## Success metrics


Collect at least ten distinct participant observations for the ordinary mobile journey. Time simple score entry only, excluding play and independent review. Record participant pseudonym, completion, assistance, correct save-location explanation and elapsed score-entry seconds.

The acceptance evaluator expects:

- `users`: observations with `participant`, `completed`, `assisted`, `save_location_correct`, `score_entry_seconds`.
- `interruptions`: all eight named scenarios, each with `executed`, `lost_acknowledged_saves`, `duplicate_submissions`, `silent_overwrites`.
- `keyboard` and `viewport_360`: booleans for `official_accept_venue`, `court_score_submit`, `organiser_replace`.

```bash
python ci/evaluate_mobile_matchday.py observations.json --output mobile-acceptance.json
```

It fails missing evidence, repeated participant IDs, incomplete timing evidence and any failed gate. Required: at least 90% unassisted completion, at least 90% correct save-location understanding, median simple entry under 60 seconds, zero integrity failures across the defined suite, all critical 360px journeys and all critical keyboard journeys passed.
