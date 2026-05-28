Sports Federation Venues
========================

Venue, playing-area, and round scheduling support. Tracks physical locations
where matches are held, including address, capacity, facilities, individual
playing surfaces, and round-level venue assignment.

Purpose
-------

Centralizes venue information so tournaments, rounds, and matches can use
structured location data instead of free-text fields. Playing areas let a
single venue, such as a sports complex, contain multiple usable surfaces.
Rounds carry the shared schedule metadata for a block of matches: the calendar
date and venue live on the round, while each match keeps its own exact kickoff
time.

Dependencies
------------

- ``sports_federation_base``: Core entities.
- ``sports_federation_tournament``: Tournaments and matches.

Models
------

``federation.venue``
~~~~~~~~~~~~~~~~~~~~

A physical location such as a stadium, sports hall, or complex.

Fields:

- ``name`` (Char): Venue name.
- ``street`` through ``country_id`` (Address): Full postal address.
- ``contact_name`` / ``contact_email`` / ``contact_phone`` (Char): On-site
  contact details.
- ``capacity`` (Integer): Total spectator capacity.
- ``equipment_notes`` (Text): Available equipment.
- ``playing_area_ids`` (One2many): Courts, pitches, and other playable areas.
- ``blackout_window_ids`` (One2many): Venue or playing-area blackout windows.
- ``playing_area_count`` (Integer): Stat-button counter.
- ``blackout_window_count`` (Integer): Stat-button counter.
- ``notes`` (Text): General notes.
- ``active`` (Boolean): Whether the venue is in use.

``federation.playing.area``
~~~~~~~~~~~~~~~~~~~~~~~~~~~

A single playing surface within a venue.

Fields:

- ``name`` (Char): Area label such as ``Pitch 1``.
- ``venue_id`` (Many2one): Parent venue.
- ``code`` (Char): Short code.
- ``capacity`` (Integer): Surface-specific capacity.
- ``surface_type`` (Selection): ``grass``, ``artificial``, ``indoor``,
  ``clay``, or ``other``.
- ``capability_ids`` (Many2many): Capability tags such as lighting,
  streaming, or sport-specific equipment.
- ``active`` (Boolean): Whether the area is available.
- ``notes`` (Text): Remarks.

``federation.playing.area.capability``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A reusable tag that describes what a playing area can support.

Fields:

- ``name`` (Char): Capability label.
- ``code`` (Char): Stable short code.
- ``description`` (Text): Optional operator notes.

``federation.venue.blackout``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A closure or blackout window that makes a venue or one playing area unavailable.

Fields:

- ``name`` (Char): Operator-facing label.
- ``venue_id`` (Many2one): Affected venue.
- ``playing_area_id`` (Many2one): Optional specific playing area.
- ``date_start`` / ``date_end`` (Datetime): Closed interval.
- ``reason`` (Selection): ``blackout``, ``maintenance``, or ``other``.
- ``notes`` (Text): Optional scheduling notes.

Inherited Extensions
--------------------

- ``federation.tournament`` gains ``venue_id`` and ``venue_notes`` for
  tournament-wide venue planning notes plus
  ``required_playing_area_capability_ids`` for divisions that need specific
  courts.
- ``federation.tournament.stage`` surfaces linked ``round_ids`` so stage admins
  can plan sequence, date, and venue directly on rounds.
- ``federation.tournament.round`` gains ``venue_id`` alongside the base
  ``round_date`` field from the tournament module.
- ``federation.match`` gains ``venue_id`` and ``playing_area_id``. When a
  match is linked to a round, the round becomes the authoritative shared
  venue/date scope.

Key Behaviours
--------------

- **Structured addresses**: venues store full addresses with country
  references.
- **Multi-area venues**: a sports complex can have several pitches or courts.
- **Constraint windows**: venues can declare blackout or maintenance windows at
  venue or playing-area level.
- **Capability tags**: playing areas can advertise the operational capabilities
  they support, and divisions can require matching capabilities.
- **Round-owned schedule planning**: administrators can create stage rounds up
  front and assign a date and venue to each one without duplicating scheduling
  concepts.
- **Match to round consistency**: assigning a round to a match propagates the
  tournament and stage scope, applies the round venue, and rejects conflicting
  venue or date combinations.
- **Duplicate-pairing guardrails**: teams in the same category cannot play the
  same opponent more than once inside the same round.
- **Competition Workspace integration**: when
  ``sports_federation_competition_engine`` is installed, blackout windows,
  maintenance closures, and capability mismatches feed planner validation and
  venue-readiness summaries.
- **Finance bridge integration**: when ``sports_federation_finance_bridge`` is
  installed, scheduling a match with a venue automatically creates or reuses a
  draft venue-booking charge for passthrough settlement.
