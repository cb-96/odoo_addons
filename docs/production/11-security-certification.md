# Package 11: workflow and security certification

## Canonical release journeys

- Club: team → season registration → tournament registration → returned correction → roster → official duty → match sheet → result review → action inbox.
- Manager: competition → division → registrations → tournament flow → entries → matches → gamedays → slots → validate → publish → results → close.
- Multi-stage: groups → frozen standings → championship and placement progression → downstream scheduling → publication.

## Required identities

Anonymous, unscoped portal, foreign-club representative, team representative, club representative, referee, federation user, planner, manager and administrator.

## Gate

All cross-club identifier-substitution tests must deny access. Every modifying HTTP route must be authenticated, state-checked, ownership-scoped and CSRF-protected. No critical or high security finding may remain open.
