# Competition usability implementation

Based on the uploaded working tree on branch `workflow-improvement`, commit
`7667e752e90395f72cce82a11af8226d204b1950`. The patch targets the supplied
uncommitted source, not a clean checkout of that commit. Existing changes are preserved.

## Included

1. Shared caller-scoped task identities for planner counts and destinations. Missing
   rosters count as teams; missing lineups count as game days; official coverage counts
   matches, including matches with no assignments. Completed results awaiting approval
   remain visible. Closed/cancelled days are excluded from the active operations list.
   Actual match-day readiness contributes to the planner; unavailable checks are not ready.
2. Missing roster actions create/reuse the correctly scoped roster only when clicked.
   Official coverage opens the existing match-day assignment wizard, preserving existing
   assignments. Submitted lineups open their review record rather than another draft wizard.
3. Additional creation settings and technical division codes are hidden by default.
   Format confirmation displays match totals, league matches per team and knockout byes.
   Confirmation is explicit and a changed participant snapshot requires reopening.
4. `/my/preparation` joins confirmed registration, roster creation, roster feedback,
   pending lineups and player consent-document links. All commands use existing portal
   ownership and approval boundaries. Consent upload is not represented as approval.
5. Focused match-day operations form and result queue. Quick result entry supports Save
   Draft and governed Submit, including score confirmation and explicit 0-0 confirmation.
   Existing result periods still must reconcile; use the full match form for period editing.
6. Explicit server-side competition creation drafts under My Creation Drafts, owned by
   their creator. Successful creation removes the saved draft. Lineup selection recovery
   is session-only, user/action-scoped and expires after 24 hours; names, free text, files,
   passwords and tokens are excluded. Result drafts persist on the match. A novice test
   protocol and regression tests are included. Actual novice sessions have NOT been run.

## Install on staging first

Back up the database and current working tree. From the repository/addons root:

```sh
git apply --check competition_usability.patch
git apply competition_usability.patch
python ci/check_usability_patch.py
node ci/check_draft_recovery.cjs
```

Alternatively replace only the three included addon directories with their ZIP versions.
Do not both apply the patch and overwrite directories. Keep all other addons unchanged.
Restart the application and upgrade:

```sh
odoo -d YOUR_STAGING_DATABASE -u sports_federation_rosters,sports_federation_setup_flow,sports_federation_portal --stop-after-init
```

The setup addon now explicitly depends on rosters, officiating and result control.
These dependencies already exist in the supplied repository. Run its normal full CI
and Odoo test suite before production. Refresh backend and frontend asset bundles.

## Validation performed here

- Five dependency-free source/behavior tests passed, including preview calculations.
- Eight JavaScript recovery behavior assertions passed.
- Python/XML parsing passed for the three changed addons.
- New inherited XPath targets were checked against the supplied parent templates.
- 168 relevant baseline files were compared with the uploaded JSONL: no differences.
- Patch applicability and archive integrity checked during packaging.

Odoo is not installed in this execution environment. Registry installation, view validation,
record-rule integration, browser rendering, concurrent transactions and Odoo regression
execution are NOT certified by these checks. The included Odoo tests must run on staging.

## Deliberate limits

Creation drafts use explicit Save Draft, not automatic saving on every keystroke; the
standard form still requires its mandatory fields before saving. Lineup recovery is confined
to the same browser tab/session. Uploads must be selected again. Consent documents and
personal notes are never cached by recovery. The preparation queue shows at most 100
pending sheets with a link to the complete list. Backend task counts respect caller record
rules; they are not a privileged federation-wide audit. Independent review remains required
where the competition policy requires it. No production database was modified.
