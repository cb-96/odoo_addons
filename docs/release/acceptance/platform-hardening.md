# Platform hardening acceptance

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

Acceptance scenarios for court-cache precedence, revision-bound document
review, operational job claiming and retry, finance company and lifecycle
boundaries, renewal metadata, the opt-in scope of member services and native
accounting, and projection/command separation.

The default installation is `sports_federation_app`; member services and
native accounting are opt-in and must be installed explicitly. Finance and
disciplinary ownership are company-scoped; this does not mean every sporting
model supports independent multi-tenant federations.

## Migration behaviour to verify


- Legacy document approvals require revision-bound re-review. Previous reviewers are
  retained in chatter, but current verification metadata is cleared. Missing document
  evidence requires replacement. Every new upload increments a revision and hashes bytes.
- A stale review snapshot cannot approve replacement evidence. The reviewer must inspect
  their own immutable snapshot and explicitly confirm inspection. Expired evidence is rejected.
- Known company ownership is preserved. Single-company legacy rows can be mapped automatically.
  Ambiguous multi-company fee/event/case ownership aborts upgrade. Explicitly map ownership
  in an audited staging migration; split fees spanning companies. Do not guess assignments.
- Native accounting activation/upgrade refuses settled unlinked customer charges. Map and
  reconcile legacy obligations through an audited migration rather than forging invoice links.
- Customer charges require a posted, fully paid native invoice before settlement. Draft or
  partial credit notes cannot resolve a charge. A full posted linked reversal can resolve it.
  Credits/reimbursements retain external handoff settlement; no elevated invoice fallback remains.
- Finance summary CSV appends Company and Currency after the original five columns.
  Totals are partitioned by both company and currency.

## Local checks


```bash
python ci/static_checks.py
node --check sports_federation_live_workspace/static/src/workspaces.js
node ci/test_court_cache.mjs
python ci/test_candidate_acceptance.py
python ci/check_usability_patch.py
python ci/check_application_entrypoint.py
git diff --check
```

## Exact-commit runtime qualification


Use the existing `ci/release_confidence.py` orchestration and real scenario adapters
with an approved sanitized backup. Do not substitute echo commands or fabricated logs.

1. Fresh core installation: verify opt-in addons are absent by default.
2. Fresh opt-in installation in a separate accounting-configured database. Run
   `sf_release_confidence` and `sf_member_services` tests. Configure a real company
   chart, sales journal, product accounts and taxes. Keep external-handoff core
   expectations separate from native charge lifecycle expectations.
3. Upgrade the baseline database and installed affected addons: base, discipline,
   finance bridge, reporting, setup flow, portal, live workspace, app, and installed
   opt-in addons. Verify attachment bytes/checksums before and after upgrade and rollback.
4. Seed legacy approved documents, including missing evidence, and test re-review migration.
   Exercise known single-company mapping and deliberate ambiguous multi-company refusal.
5. Run `TestJobClaiming.test_two_cursors_cannot_claim_one_job`. Race ensure-job, renewal
   and invoice commands with independent transactions; allow Odoo serialization retry
   and assert exactly one durable business record.
6. Inject callback mutation followed by failure. Verify mutation rollback, one recorded
   attempt, backoff, stale recovery, terminal rejection and completed recovery replay.
7. Test company-scoped read/search/RPC/export isolation for obligations, fees, cases,
   sanctions and all three finance reports. Reject cross-company payer/product/source
   links and direct handoff audit metadata writes.
8. Exercise invoice draft/post/payment/full reversal/partial reversal/cancellation using
   real Accounting commands, not forged payment-state fields. Check direct-write guards,
   invoice-reference parity and repeated/concurrent command idempotency.
9. Browser-test clean cache versus newer server scores, dirty recovery, pending receipt
   replay, corrupt/unavailable storage, network loss and stale signatures. Preserve evidence.
10. Open review snapshot A, return/upload B in another session, then confirm A. It must
    fail without approving B. Independently inspect/verify B. Repeat after access revocation
    and document expiry.

## Observed novice, mobile and keyboard acceptance


Use a real first-time participant and observer. Record candidate SHA, role, task,
viewport, browser/device, timestamps, assistance, failures and recovery. Avoid recording
personal document contents in screenshots.

- Novice organiser: create competition, find next step, register teams, preview/publish schedule.
- Novice club user: find membership/entry, upload evidence, distinguish review from eligibility,
  renew an active membership and find the resulting draft.
- Reviewer: inspect exact snapshot and recover from a stale decision without approving wrong bytes.
- Mobile court operator: enter scores at narrow viewport, lose connectivity, reload/reconnect,
  reconcile without duplicate submission or lost local evidence.
- Keyboard-only: complete critical journeys with Tab/Shift+Tab/Enter/Space, visible focus,
  reachable dialogs/downloads, no focus traps and understandable error/focus recovery.

A coached walkthrough is not novice acceptance. A Node regression test is not browser,
mobile or keyboard acceptance. Record failures honestly and retest on the corrected commit.

## Fail-closed evidence gate


Copy `ci/candidate_acceptance.template.json` into the run evidence directory. Leave
unexecuted categories pending. Populate only actual results with execution timestamps,
commands or observer/participant/device details, and relative artifact paths plus SHA-256.

```bash
python ci/check_candidate_acceptance.py --commit "$(git rev-parse HEAD)" --evidence /path/to/run/candidate_acceptance.json
```

All nine categories must pass on the exact candidate. This validates evidence integrity,
not the truth of an unobserved human claim; retain accountable release sign-off.
