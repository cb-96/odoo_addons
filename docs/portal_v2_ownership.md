# Portal V2 ownership

The portal is a projection of V2 competition records. It does not own a second
competition lifecycle and does not fall back to legacy tournament workspaces.

| Portal concern | Authoritative model |
|---|---|
| Competition | `federation.competition.edition` |
| Registration | `federation.competition.entry` |
| Participation | `federation.participant.set` |
| Fixture | `federation.fixture` |
| Physical day | `federation.matchday` |
| Schedule visibility | current live `federation.schedule.publication` |
| Live execution | `federation.matchday.session` |
| Result | fixture-linked `federation.match` |
| Standings | `federation.standing` |

Draft schedules, review evidence, approval notes and superseded publications are
not portal schedule sources. Portal access remains scoped through represented
clubs and teams and through `federation.portal.privilege` for mutations.
