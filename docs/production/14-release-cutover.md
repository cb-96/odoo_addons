# Package 14: Release engineering and cutover

## Required gates

1. `python ci/static_checks.py`
2. JavaScript syntax and frontend tests
3. Fresh-database addon installation
4. Upgrade from a restored previous-release database
5. Full Odoo tests through `ci/run_odoo_tests.sh`
6. Competition integrity and operational-health checks
7. Immutable artifact smoke test
8. Backup and restore rehearsal

## Cutover

Record the artifact checksum. Back up the paired PostgreSQL database and filestore. Stop writes, deploy the tested artifact, upgrade modules in dependency order, run health and integrity checks, and verify login, portal scope, registrations, rosters, Schedule Planning, Tournament Flow Builder, publication, match-day operations, results, notifications, and scheduled jobs.

## Rollback triggers

Data loss, authorization bypass, failed migration, failed restore, incorrect schedule/result/standings, unavailable critical journey, or a blocking integrity finding.

## Rollback

Stop traffic, retain diagnostic evidence, restore the paired database and filestore, deploy the previous immutable artifact, run health checks, and execute canonical smoke journeys before reopening traffic.
