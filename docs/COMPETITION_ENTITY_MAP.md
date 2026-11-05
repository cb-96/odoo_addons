# Authoritative competition entities

The normal operator journey is **Competition -> Teams -> Format -> Game days -> Schedule -> Publish -> Play -> Finish**. Internal engine records remain available to advanced operators but do not define the normal workflow.

- **Competition**: recurring competition identity. Master data, closed/archived administratively.
- **Edition**: one season's competition lifecycle and roles. Derived from competition + season; finish/archive owns closure.
- **Division**: playing group and division rules. Derived from edition and follows its lifecycle.
- **Registration Window**: application round. Finalization owns the handoff to participants.
- **Participant Set**: finalized team list used by format. Derived from approved entries; replacements supersede history.
- **Participant**: team's confirmed place in a division. Derived from the participant set; withdrawn rather than reinterpreted.
- **Structure**: versioned playing format. Derived from participant set; freeze makes it authoritative for fixtures.
- **Stage**: one phase of a structure. Derived from structure and progression rules.
- **Fixture**: logical who-plays-whom pairing. Derived from stages/results; cannot disappear once operationalized.
- **Game Day**: date, venue, capacity and live operational state. Derived from edition planning.
- **Slot**: playable court/time on a game day. Derived from game-day capacity.
- **Schedule**: working fixture-to-slot plan. Derived from frozen fixtures and slots; publication closes a revision.
- **Publication**: immutable reviewed snapshot of a schedule. Superseded, never rewritten.
- **Match**: the game actually played, including live state and result. Materialized from a resolved fixture and linked to publication.

Every lifecycle handoff has explicit postconditions in `federation.lifecycle.postconditions`.
