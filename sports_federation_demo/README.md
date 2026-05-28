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
- Data is versioned with the addon and intended to stay reproducible across installs.

Validation checklist
- Module installs without additional manual data steps.
- Tournament, roster, and standings flows are navigable from seeded records.
- Portal/public pages can render at least one realistic competition storyline.
