# Public Competition API

Owner: Federation Platform Team
Last updated: 2026-09-04

Clubs can consume non-sensitive published data through:

```text
GET /api/v1/competitions
GET /api/v1/competitions/<edition-slug>
```

The detail feed aggregates published divisions, teams, schedule sections,
approved results, standings, brackets, and canonical links. It excludes contact
details, personal data, internal notes, discipline records, unpublished
schedules, and unapproved results.

Responses advertise contract version `v1` and allow 60-second caching. Club
representatives use **My Account > Data API** or `/my/data-api` for live examples.
