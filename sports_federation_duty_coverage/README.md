# Official Duty Coverage

This addon extends referee assignments with eligibility, availability,
acceptance, attendance, and replacement controls. The owning match and
assignment workflows remain authoritative for publication and officiality.

## Official mobile check-in

Officials may request check-in only for an assignment they can read. The
assignment command validates that access before reading its linked match under
scoped elevation to calculate the current-publication and slot signature. Only
the digest is returned to the caller. A check-in request is not confirmed
attendance; an authorised organiser records attendance through the manager
command.

## Security and verification

Assignment writes, coverage decisions, and attendance confirmation remain
manager-authorised model commands. Regression coverage includes denied
unauthorised official actions and stale publication/signature behavior. Run
this addon’s Odoo tests through `bash ci/run_tests.sh --module sports_federation_duty_coverage`.
