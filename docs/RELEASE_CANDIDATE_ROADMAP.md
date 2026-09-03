# Release Candidate Roadmap

Owner: Federation Platform Release Owner
Last updated: 2026-09-03
Review cadence: Every candidate

## Scope freeze

Status: **Active**

Only release blockers, security or integrity defects, accessibility regressions, and evidence gaps may change the committed candidate.

## Required qualification

- versioned role and prohibited-permission matrix;
- recovery inventory for registration, schedule review, publication replacement, job retry, and standings correction;
- certified demo federation with clubs, teams, rosters, played matches, results, and standings;
- integrated lifecycle, keyboard, portal, public-site, and release-focus acceptance tours;
- useful empty states and prevention of raw workflow values in user-facing templates;
- small, medium, and large performance profiles for 10, 100, and 500 clubs;
- clean install, full addon upgrade, full suite, and migration rehearsal against an approved backup;
- copy-link, bounded recent-items, and contextual next-action portal shortcuts.

## Candidate execution

```bash
scripts/ci/run_release_candidate.sh --backup-dir /approved/backup/directory
```

Approval requires all lanes to pass on the exact committed SHA, no unresolved release blocker, complete baseline and migration evidence, and release-owner sign-off.
