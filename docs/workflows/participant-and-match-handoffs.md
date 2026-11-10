# Participant and match handoffs: implementation and qualification

## Baseline and apply

These are incremental patches after the reviewed annual-player registration,
edge-case tests, and membership/division boundary patches from this conversation.
They target the reconstructed supplied source snapshot, not a newly fetched live repo.
Apply participant_handoff.patch and match_journey.patch; each changes its own addon.
Upgrade sports_federation_registration and sports_federation_schedule_approval together
with their installed dependencies in a disposable QA database first.

## Participant handoff implemented

- Existing finalization now locks the division/window, checks approved team eligibility,
  records actor/time/digest, and replays without duplicating the finalized snapshot.
- Review dialog captures an entry digest; stale review is rejected.
- Finalization creates confirmed participants with source entry and snapshot links.
- Finalized entries, snapshots and managed participant identities cannot be independently
  edited/deleted through the ordinary workflow.
- Amend finalized teams requires a reason and expected snapshot. It uses the existing
  conservative team-selection command, creates a successor snapshot, preserves the old
  snapshot, synchronizes accepted/withdrawn participants, and emits an amendment event.
- Another registration window cannot silently replace the division's current finalized list.
- Migration backfills source links only for unambiguous current approved entries; no
  participants, approvals or results are fabricated.

## Match journey implemented

- Fixture-based workspace displays pairing, stage, division, operational state,
  publication provenance and schedule allocation history, with links to play/results.
- Published operational match kickoff/location/publication pointers are command-owned.
  Publication handoff supplies a private in-process token; client context cannot forge it.
- Publication replay returns the same live publication instead of duplicating it.
- Same-game-day rescheduling captures the expected publication, rejects stale/no-op/
  occupied-slot/started-match changes, prepares a replacement schedule revision and
  runs the existing capacity/conflict/rest validator.
- The live publication and match remain unchanged until the existing review/approval/
  publication flow completes. Independent approval is not bypassed.
- Started/completed matches cannot be moved by publication; unchanged ones retain
  their original publication provenance.

## Deliberate limits: not the entire earlier roadmap

These patches implement the core handoffs and safe operator paths, not every proposed
advanced amendment scenario. In particular:

- Team additions/replacements/withdrawals through the new amendment command are blocked
  once any format depends on the snapshot. A full post-format successor-format workflow,
  post-publication participant amendments, and post-start sporting withdrawal rules are
  NOT implemented here. No result inheritance is inferred.
- Cross-game-day rescheduling is NOT implemented in the new dialog. It requires a
  coordinated amendment of both days and their fixture allocations/publications.
- Replays/additional fixture occurrences and automatic adjudication of upstream result
  corrections affecting started downstream matches are NOT added.
- Existing publication events/notification mechanisms are reused; no new durable
  notification outbox or notification retry subsystem is added.
- The workspace is linked from the normal match form. Existing planner/portal click paths
  are not all rewritten into this view.

## Tests and validation

Added Odoo transaction tests: finalization replay/source links, stale entry digest,
immutable finalized entry/snapshot, amendment history/reason/current revision,
managed participant state guard, conflicting windows, publication replay, direct kickoff
write rejection, workspace navigation, stale/no-op rescheduling, and valid amendment
preparation without changing the live match.

Passed: addon integrity, ACL CSV integrity, Odoo test discovery, changed Python/XML
syntax, inherited-view XPath targets, and both patches' git apply --check --whitespace=error.

NOT executed: Odoo runtime tests, installation/upgrade, SQL migration rehearsal,
browser tests, independent-session concurrency tests, or full release qualification.
Odoo is not installed in this environment. New tests are included, not claimed passing.
Existing test fixtures that directly edit finalized snapshots or bypass annual licences
need explicit review. Translation extraction is also required.

## QA command flags

Use your configured QA Odoo command with:

    --test-enable --test-tags sf_handoffs,sf_boundaries,sf_season_players --stop-after-init

Then run the complete suite, role/security tests, browser qualification, migration
rehearsal and multi-session concurrency tests. Inspect duplicate finalized windows
and ambiguous legacy source links before upgrade. Verify publication and live operational
commands against the new match write guard. Do not deploy based on static checks alone.

## Commit messages

feat(registration): govern participant finalization and team-list amendments
feat(scheduling): unify match workspace and reviewed rescheduling handoffs
