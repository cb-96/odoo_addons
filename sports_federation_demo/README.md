# sports_federation_demo

Deterministic demo-data pack for the Sports Federation Odoo addons.

Purpose
- Seed a development or showcase database with realistic federation records.
- Provide a repeatable baseline for onboarding, manual QA, and guided product demos.

What it loads
- Clubs, teams, players, seasons, registrations, tournaments, participants, and matches.
- Supporting records used by rosters, standings, compliance, discipline, and notifications.

How to use
1. Install the module with demo data enabled in Odoo.
2. Open core workflows from tournament setup through match completion.
3. Reset by recreating the database when you need a fresh deterministic dataset.

Scope and constraints
- This module is for non-production environments.
- Demo records prioritize workflow coverage over real-world data volume.
- The seeded Spring Cup intentionally omits category and gender restrictions
  because its participant fixture demonstrates senior, youth, and women's
  teams in one navigable competition.
- Data is versioned with the addon and intended to stay reproducible across installs.

Validation checklist
- Module installs without additional manual data steps.
- Tournament, roster, and standings flows are navigable from seeded records.
- Portal/public pages can render at least one realistic competition storyline.

## Release-pilot qualification

The integrated P0-P3 release path is documented in
`docs/RELEASE_PILOT_SCENARIO.md`. Run
`scripts/ci/run_rc_validation.sh focus` before promoting a release candidate.

## Accessible operator training walkthrough

Use the deterministic demo database with a federation manager who also has the
competition administrator, registration manager, competition designer, calendar
planner, schedule planner, schedule approver, and match-day manager roles.

Complete the normal path without a mouse:

1. Open **Competition Overview** and move through controls with `Tab` and
   `Shift+Tab`. The focused control must always have a visible outline.
2. Continue through **Registration**, **Format**, **Calendar**, **Schedule**, and
   **Review**, activating links and buttons with `Enter` or `Space`.
3. Submit an incomplete portal form. Focus must move to the error summary, and
   invalid controls must reference that summary through `aria-describedby`.
4. Open and close a confirmation modal. Focus must enter the modal and return to
   the control that opened it.
5. Repeat the club portal's competition, roster, officiating, and result tasks at
   a 390 CSS-pixel viewport. No primary action may require horizontal page
   scrolling.
6. Confirm that every state is expressed as readable text. Color and icons may
   reinforce the state but must not be the only status signal.

The `keyboard_competition_setup` browser tour qualifies the canonical backend
journey mechanically. Portal template accessibility and mobile tests qualify
labels, error semantics, status text, responsive tables, and action wrapping.
