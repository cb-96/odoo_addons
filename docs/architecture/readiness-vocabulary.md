# Readiness vocabulary and game-day readiness

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

Volunteers see one language for "is this fine?" everywhere in the platform.
Detailed lifecycle states stay in the models; only the words shown to people are
shared.

## The six words

| Status (code)      | Label              | Meaning                                              |
| ------------------ | ------------------ | ---------------------------------------------------- |
| `ready`            | Ready              | Everything required is in place.                     |
| `action_needed`    | Action needed      | Somebody has to do something, and we say what.       |
| `waiting_review`   | Waiting for review | Submitted; another person has to review or approve.  |
| `blocked`          | Blocked            | A failed condition stops progress until resolved.    |
| `complete`         | Complete           | The work is finished and closed.                     |
| `not_applicable`   | Not applicable     | Nothing is required here.                            |

The words live in `sports_federation_base/readiness_vocabulary.py` (plain
Python) and are translated by the `federation.readiness.vocabulary` service.
Never write these labels, or the legacy variants they replaced ("Checked",
"Not checked", "Not fully checked", "Current checks complete", "Needs action"),
as free text on a readiness surface. Ask the service.

## How internal states map

`STATE_MAPPINGS` translates a detailed state into a shared status. Unmapped
states become `action_needed`; they are never reported as ready.

| Domain        | Internal states → shared status                                                                                   |
| ------------- | ------------------------------------------------------------------------------------------------------------------ |
| `coverage`    | `unchecked`, `uncovered`, `needs_action` → action needed; `ready` → ready; `not_required` → not applicable         |
| `journey`     | `action`, `unknown` → action needed; `waiting` → waiting for review; `complete` → complete; `not_applicable` → n/a |
| `eligibility` | `pass` → ready; `fail` → blocked; `review_required` → waiting for review; `not_applicable` → not applicable        |
| `compliance`  | `compliant` → ready; `missing`, `expired` → action needed; `pending` → waiting; `non_compliant` → blocked          |
| `lineup`      | `not_started`, `draft`, `rejected` → action needed; `submitted` → waiting; `approved` → ready; `locked` → complete |
| `roster`      | `draft` → action needed; `active` → ready; `closed` → complete                                                     |
| `schedule`    | `draft`, `changes_requested`, `approved` → action needed; `ready_for_review` → waiting; `published` → ready       |
| `court`       | `available` → ready; `delayed` → action needed; `unavailable` → blocked                                            |

`ci/check_readiness_vocabulary.py` reads the selection fields of these models
and fails when a state has no mapping.

## Can this game day run?

`federation.matchday.readiness` (owned by `sports_federation_matchday`) is the
only place that answers this question.

```
Schedule          Ready
Rosters           8 / 8 ready
Line-ups          7 / 8 ready
Officials         22 / 24 ready
Courts            Ready
Eligibility       Ready
Compliance        Ready
Overall: ACTION NEEDED
```

Each addon that owns a part of the game day registers one provider by extending
`_readiness_providers()`:

| Component     | Provider addon                                   |
| ------------- | ------------------------------------------------ |
| `schedule`    | `sports_federation_matchday`                     |
| `courts`      | `sports_federation_matchday`                     |
| `rosters`     | `sports_federation_rosters`                      |
| `lineups`     | `sports_federation_rosters`                      |
| `eligibility` | `sports_federation_rosters`                      |
| `officials`   | `sports_federation_officiating`, replaced by the acceptance-aware provider in `sports_federation_duty_coverage` when installed |
| `compliance`  | `sports_federation_compliance`                   |

Aggregation: blocked beats action needed beats waiting for review. Only an
all-ready day can run. A provider that fails is reported as blocked, never as
ready.

Consumers, all calling the same `evaluate()`:

- competition planner: `get_planner_matchday_readiness()` (loaded separately so
  list guidance stays cheap);
- backend match-day form: "Can this game day run?" panel;
- live workspace: `federation.court.commands.load()` returns `brief()`, which
  leaves out owners and links;
- release gate: `sports_federation_app/tests/test_matchday_readiness_release.py`.

## Actionable blockers

Every status other than ready, complete and not applicable carries at least one
blocker, and every blocker states:

- **problem** - what is wrong, in plain words ("1 game-day line-up still needs
  to be submitted.");
- **owner** - who acts. A missing owner stays visible as "No owner assigned";
- **deadline** - by when. A missing deadline stays visible as "No deadline set";
- **action** - what to do;
- **destination** - the record, or list of records, where to do it.

`make_blocker()` and `make_component()` reject anything less, and the contract
check fails any `make_blocker(...)` call without these keywords.

## Adding a component or a state

1. New internal state: add it to the matching `STATE_MAPPINGS` domain.
2. New game-day component: add its key to `COMPONENT_ORDER` and the provider
   table in `ci/contracts/readiness_vocabulary.json`, then register
   `("key", "_readiness_key")` in the owning addon.
3. New readiness surface: list it under `surfaces` in the contract so legacy
   wording cannot return.

## Deliberately unchanged

Notification delivery states, schedule-approval review queues, compliance
and finance lifecycle lists, and every other model's detailed states keep their
own lifecycle vocabulary. They are not readiness answers; notification delivery
is covered by the notification lifecycle work.

## Test coverage

| Evidence | Covered by |
| -------- | ---------- |
| STATIC   | `ci/check_readiness_vocabulary.py`, `ci/test_readiness_vocabulary.py`, `ci/test_readiness_surfaces.py` |
| ORM      | tagged `sf_matchday_readiness` tests in base, matchday, duty coverage, setup flow and app |

Static contracts do not prove the screens render. Browser and human acceptance
are still required before release.
