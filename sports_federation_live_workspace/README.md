# Court Operations and Visual Planning

Implementation candidate, not a staging acceptance certificate.

## Installation
Install or upgrade the supported `sports_federation_app` entry point. Its dependency graph now includes this addon. Apply the incremental patch only to the supplied current source baseline. Do not reapply earlier patches: their release-confidence, journey and duty-coverage code is already in that baseline.

## Court operation
1. Configure aggregate, period-total or sets-won scoring on the competition edition. Configure a winning set target where applicable.
2. Publish through the existing independent schedule review and publication workflow.
3. Open the canonical match-day session and assign named internal court operators.
4. Operators open Match Day > Run this court, select their court, inspect lineups and separate accepted/eligible/present official facts, save drafts, then submit for result review.
5. Submission is not approval. Existing verification, approval, corrections and standings controls remain authoritative.

## Connectivity contract
Offline capture is supported in an already loaded, authenticated workspace. This is not a cold-start offline PWA: opening the application or an uncached match requires connectivity. Device drafts and queued commands are stored under database/user/court/match-specific localStorage keys. No birth dates or contact details are cached. Use dedicated trusted devices; localStorage is not encrypted and a shared unlocked browser is not an access boundary.

Each command carries an actor-bound content receipt, expected draft revision and schedule/result signature. Retry exactly the same key and payload after a lost response. A batch is atomic. A stale draft, changed publication, changed score, revoked operator or closed session stops synchronisation. No automatic score merging occurs. Export evidence before explicitly discarding the local queue or acknowledging a changed context. Exported evidence is not an authoritative result and is never automatically imported.

Interrupted matches retain drafts for resumption. Disputed and abandoned captures raise linked incidents and retain a coordinator hold, even if an operator later changes the outcome back to normal. Match-day managers use Court recovery and exceptions > Resolve exception to record a reasoned resume or abandonment decision. Confirmed abandonment creates no official score. Forfeits require a reason and a score favouring the non-forfeiting team, then follow ordinary independent result review.

## Visual planning
Open a schedule and select Visual planning. The workspace projects existing stages, progression ranks, fixture sources and a court/time grid. Select a fixture and preview a manual move; applying it pins the assignment. Regeneration retains non-automatic assignments. Team/court unavailable windows and hard minimum rest are distinct from fairness preferences.

Every preview is stored server-side, belongs to its actor and contains the exact candidate map. Before/after views show changed slots, unallocated fixtures, hard failures, warnings and weighted fairness penalty (lower is better). Apply revalidates the map and signature, performs one governed revision and retains the preview. Rejected-slot explanations do not misrepresent a heuristic solver as a proof of infeasibility.

Published schedules cannot be edited here. Create a governed amendment, then return to the existing independent review/publication controls. Live operations must be closed before replacement publication. Practical constraints copy to amendment revisions.

## Verification
Standalone: `python -m unittest discover -s ci -p test_live_workspace_policy.py`.
Installed application: run Odoo tests tagged `sf_live_workspace` and the existing `sf_release_confidence` suite on fresh and upgraded disposable databases. The addon includes persisted command tests and real backend browser journeys. Database, HTTP/browser and independent-transaction concurrency tests were not executed in the authoring environment because Odoo/PostgreSQL and a staging connector were unavailable.

Keep production rollout blocked until fresh installation, upgrade, complete browser journeys, independent-transaction races, backup plus filestore restoration, monitoring recovery, fallback rehearsal and novice-user observations have actual evidence. The supplied acceptance audit distinguishes implementation from demonstrated acceptance.

## ACL registration correction

Version 19.0.1.0.1 registers the unchanged ACL rows through the standard
security/ir.model.access.csv filename. The former access.csv is removed.
Existing ACL external IDs and permissions are preserved. Upgrade this addon
on staging so the corrected data registration is loaded.
