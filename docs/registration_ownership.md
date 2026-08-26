# Registration cutover

The authoritative chain is `federation.registration.window` →
`federation.competition.entry` → `federation.participant.set`. Public
registration resolves the open window for the selected division and enforces
club ownership, eligibility, duplicate-entry and capacity rules.

The portal 19.0.5.0.0 migration drops the test-only V1 tournament-registration
table. Take a verified backup before upgrading. Federation staff review entries
through **Competition Engine → Registration Desk**.
