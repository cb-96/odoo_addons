# Annual player registration: tests and edge-case review

## Added tests

Real Odoo transaction tests now cover the full sequence: collect players, submit,
reject a pending player from a roster, approve, create eligible roster lines,
confirm player charges, create a grouped draft club invoice, and replay approval
without duplicate charges or invoice links.

Additional regressions cover active-create wrong-club bypass, transfer before
approval, cancelled player reactivation, cancelled header reopening, no-op scope
writes, mixed-club batch atomicity, archived players, inclusive validity boundaries,
missing billing contact rollback, retained charges on cancellation, company changes
after billing, top-up invoices and missing-product invoice atomicity.

## Fixed during review

1. Creating a licence directly as active bypassed the draft-only current-club check.
   New draft/active licences now require an active player in the current club.
2. A draft licence could be approved after its player moved to another club.
   Activation now checks the current club and active player status.
3. Cancelled licences could be reactivated, and cancelled headers could be reopened
   through direct writes. Both implicit lifecycle reversals are now rejected.
4. Writing the unchanged club/season values incorrectly rejected a populated header.
   Scope protection now distinguishes a real change from a no-op write.
5. Approval, cancellation, top-ups and invoice creation did not all coordinate on
   the registration header. Added ordered row locks and refreshed licence state
   after acquiring the header lock. This is concurrency hardening, not proof that
   all race conditions are eliminated.

## Validation performed

- Changed Python syntax parsed successfully.
- Addon integrity, Odoo test discovery and portal elevated-access inventory checks passed.
- Incremental and replacement patches passed git apply --check --whitespace=error
  against reconstructed previous-patch and original-source baselines respectively.

## Runtime limitations and remaining edge cases

Odoo is not installed here. No Odoo integration tests, browser tests, database
migration rehearsal, invoice posting/payment tests or multi-session concurrency
stress tests were executed. The new tests are executable Odoo tests, not a claim
that the flow has passed release qualification.

- Run the complete suite, not just sf_season_players. Legacy fixtures without valid
  annual licences still need explicit review; do not add test-only eligibility bypasses.
- Test concurrent submit/approve/cancel/invoice operations with separate database
  sessions and transaction retries. Header locking does not lock the player's club
  assignment against a concurrent transfer or all finance-event mutations.
- Browser-level forged player IDs, CSRF, duplicate clicks and company switching
  need HTTP qualification. Existing controller scope tests are not browser tests.
- Existing migration groups licences without retrospective fees. Rehearse on a
  database copy, especially with multiple companies and inconsistent old data.
- Cancellation retains charges and invoices. Credits/refunds are explicit financial
  actions, not automatic. Verify draft cancellation and posted credit-note flows.
- Transfer/reinstatement policy remains intentionally unimplemented. Cancelled
  player-season uniqueness is retained; do not silently delete or reassign history.
- Fee schedules require category and gender for a match; missing values fall back
  to the fee default. Confirm that this matches federation pricing policy.
- Invoice tax configuration determines totals. Tests assert player price units,
  not a universal tax-inclusive invoice total.
- Translation extraction remains required; the supplied bundle lacks the language registry.

## Run

Use your configured QA Odoo command with:

    --test-enable --test-tags sf_season_players --stop-after-init

Upgrade the installed people and related addons first in a disposable QA database.
The accounting integration tests require sports_federation_accounting to be installed.
Then run the full suite and browser release qualification.

## Apply

If the previous season registration patch is already applied, use
season_registration_tests_incremental.patch.
If it is not applied, use season_registration_reviewed_full.patch instead.
Do not apply both. Neither patch changes the live repository or database here.
