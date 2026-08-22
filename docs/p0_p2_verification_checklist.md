# P0-P2 Verification Checklist

## Installation and removal
- Confirm a fresh database installs the complete V2 chain without the legacy addon.
- Confirm an existing test database can uninstall/delete the legacy addon without dangling external IDs.
- Confirm no menu, action, asset, test scope, or documentation points to the removed planner implementation.

## Ownership and data flow
- Verify V2 fixtures materialize operational matches exactly once.
- Verify Result Control is the only score lifecycle and Format Studio consumes only approved results.
- Verify configured points and tie-break rules produce expected frozen standings.
- Verify participant-set replacement invalidates only draft downstream artifacts.

## Stage graph
- Property-test brackets for 2 through 16 participants.
- Verify every team receives exactly one final placement and byes never produce fake results.
- Verify progression, carry-over, graph locking, reopen and versioning behavior.

## Calendar and scheduling
- Verify unsaved inline court slots sequence correctly without manual saves.
- Verify overlap/date constraints across timezones and daylight-saving transitions.
- Verify hard rest, consecutive-game and same-club policies.
- Verify deterministic solver output, no-capacity reporting, manual assignment preservation, and revision conflicts.
- Verify officiating feasibility blocks publication when required officials are unavailable.

## Approval and operations
- Verify planner and approver separation with distinct users.
- Verify concurrent publication cannot create two live versions.
- Verify published snapshots remain immutable and replacement requires a reason.
- Verify match-day open/incident/close permissions and audit events.

## Portal, security and observability
- Run the portal sudo guard and manually inspect the inventory exemptions.
- Verify ownership checks precede every controller-side sudo operation.
- Verify broad integration exceptions produce correlation IDs and operator-visible failures.
- Verify no silent exception path reports success.

## CI and release
- Run addon integrity, V2 readiness, workflow contracts, static checks, and full Odoo tests.
- Verify all module manifests, assets, ACLs, routes and migrations.
- Run a production-like Belgian Championship simulation end to end.
- Re-run documentation-to-code and release-candidate reviews after all checks pass.
## Removed planner-extension replacement
- [ ] Integrate referee availability, double-booking, certification and club-duty overlap into V2 schedule validation.
- [ ] Integrate venue opening, court suitability and playing-area constraints into V2 schedule validation.
- [ ] Block schedule approval/publication when required officiating or venue checks fail.
- [ ] Add transaction tests before considering functional parity complete.
