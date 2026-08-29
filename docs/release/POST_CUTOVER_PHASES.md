# Post-cutover release stabilization

The competition implementation has completed cutover. Remaining work is organized by release risk rather than historical delivery labels.

## Release gate convergence

Keep local and GitHub validation on `scripts/ci/run_rc_validation.sh`. All static contracts, fresh-install checks, upgrade checks, focused lanes and the full suite must pass before approval.

## Public projection consolidation

Keep one public route owner, neutral implementation names, explicit publication boundaries and behavior-oriented public contracts.

## Format and scheduling maintainability

Keep format generation, calendar capacity, schedule assignment, approval and match-day execution behind explicit ownership boundaries. Published schedules are immutable; amendments use reviewed replacement revisions.

## Concurrency and idempotency

Qualify publication replacement, schedule amendment, imports, result approval and background jobs under retries and concurrent requests.

## Performance qualification

Review query budgets, explain snapshots, scheduling validation runtime and public-page response budgets.

## UX consolidation

Complete two-pass reviews of administrator, club portal and public workflows. Every blocked action must explain the next corrective step.