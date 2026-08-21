# Sports Federation Base

Version: 19.0.1.2.0
Owner: Federation Platform Team
Last reviewed: 2026-08-20
Review cadence: Every release

Foundation addon for clubs, teams, seasons, and season registrations. It also provides shared security groups and infrastructure used across the federation suite.

## Responsibilities

- `federation.club`: affiliated clubs and contact data
- `federation.team`: club-owned teams by category and gender
- `federation.season`: dated federation seasons and lifecycle
- `federation.season.registration`: unique team enrollment per season
- shared manager and user security groups
- sequences, audit events, operational health, failure feedback, rate limiting, correlation helpers, and attachment policy services

## Lifecycle safeguards

- Teams must be archived before their club.
- Linked registrations must be cancelled before a team is archived.
- Open seasons must be closed or cancelled before archiving.
- Uploads are validated for extension, MIME type, size, checksum, and optional malware scanning.

## Security

- Federation User: standard read-oriented backend access
- Federation Manager: federation administration and full model management

Downstream modules must declare this addon when they import its Python helpers, reference its XML IDs, or inherit its models.

## Configuration

Settings include the optional external attachment scanner command and timeout. Production environments that require scanning must configure a scanner before enabling the mandatory-scan flag.

## Tests

The module includes attachment-policy, scanner, route-inventory, and shared infrastructure tests. Run the repository strict lint and the base module test suite after changing shared contracts.
