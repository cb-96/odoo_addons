# Court Operations and Visual Planning

Court score capture with offline recovery, mobile match-day pages for officials
and managers, the visual schedule planner and the season match board.

## Installation
Installed through the supported `sports_federation_app` entry point.

## Court operation
1. Configure aggregate, period-total or sets scoring on the competition edition. Configure a winning set target where applicable. In sets mode, a set can be drawn, and the match score is the sum of set points: **Points per won set** (default 1) and **Points per drawn set** (default 0) keep the classic sets-won score. For WDBF dodgeball, set 2 and 1 (rules 10.2-10.3) and no set target, because a match is played over two timed halves.
2. Publish through the existing independent schedule review and publication workflow.
3. Open the canonical match-day session and assign named internal court operators.
4. Operators open Match Day > Run this court, select their court, inspect lineups and separate accepted/eligible/present official facts, save drafts, then submit for result review.
5. Submission is not approval. Existing verification, approval, corrections and standings controls remain authoritative.

Officials can request check-in for their own accepted, eligible assignment from
the mobile assignment page. The request signature is computed from the current
publication, slot, match window, and assignment after validating access to that
assignment; only the resulting digest is returned. A check-in request is not
attendance. An organiser records attendance separately through the manager
command.

## Connectivity contract
There are two court apps. **Run this court** in the backend needs a loaded, authenticated workspace: it keeps working when the connection drops, but it cannot be opened offline. The **offline court app** (`/court/app`, below) starts without a network once a phone was prepared. Both use the same command service, receipts and conflict rules.

Score edits are written to the device draft as they are entered. **Save draft** queues the signed command for synchronization; queued work is sent when connectivity returns. A local draft is not an official result.

Each command carries an actor-bound content receipt, expected draft revision and schedule/result signature. Retry exactly the same key and payload after a lost response. A batch is atomic. A stale draft, changed publication, changed score, revoked operator or closed session stops synchronisation. No automatic score merging occurs. Export evidence before explicitly discarding the local queue or acknowledging a changed context. Exported evidence is not an authoritative result and is never automatically imported.

Interrupted matches retain drafts for resumption. Disputed and abandoned captures raise linked incidents and retain a coordinator hold, even if an operator later changes the outcome back to normal. Match-day managers use Court recovery and exceptions > Resolve exception to record a reasoned resume or abandonment decision. Confirmed abandonment creates no official score. Forfeits require a reason and a score favouring the non-forfeiting team, then follow ordinary independent result review.

## Visual planning
Open a schedule and select Visual planning. The workspace projects existing stages, progression ranks, fixture sources and a court/time grid. Select a fixture and preview a manual move; applying it pins the assignment. Regeneration retains non-automatic assignments. Team/court unavailable windows and hard minimum rest are distinct from fairness preferences.

The court workspace automatically opens the sole assigned court when there is
exactly one. While that initial load is in progress, further court selection is
disabled to avoid racing duplicate queue and match requests.

Every preview is stored server-side, belongs to its actor and contains the exact candidate map. Before/after views show changed slots, unallocated fixtures, hard failures, warnings and weighted fairness penalty (lower is better). Apply revalidates the map and signature, performs one governed revision and retains the preview. Rejected-slot explanations do not misrepresent a heuristic solver as a proof of infeasibility.

Published schedules cannot be edited here. Create a governed amendment, then return to the existing independent review/publication controls. Live operations must be closed before replacement publication. Practical constraints copy to amendment revisions.

## Tests
Standalone: `python -m unittest discover -s ci -p test_live_workspace_policy.py`.
Installed application: Odoo tests tagged `sf_live_workspace`,
`sf_mobile_matchday` and `sf_visual_scheduling`, plus the `sf_release_confidence`
suite, on fresh and upgraded databases. The addon includes persisted command
tests and backend browser journeys.

Staging acceptance (browser journeys, independent-transaction races, device
interruptions and novice observations) is described in the
[mobile match-day](../docs/release/acceptance/mobile-match-day.md) and
[visual scheduling](../docs/release/acceptance/visual-scheduling.md) acceptance
suites.

## Season match board

`federation.season.board` backs the `federation_season_board` client action:
every planable fixture of the competition's latest generated formats, every
active game day and its slots. The planner's Schedule step opens it.

- Commands (`move`, `unplan`, `place_on_day`, `restore`, `set_pinned`,
  `generate_slots`) need the schedule planner or competition director role. They
  also need the board signature, so a change made from a stale screen is
  refused.
- A move updates the day allocation (moving between days included) and the
  working schedule, bumps each affected schedule's revision through
  `federation.schedule.commands._resolve`, and logs `board_move` changes. All
  of this runs in one savepoint. When the schedule validator reports a new
  error, the whole move is rolled back and the errors are returned.
- Only open game days with a draft or changes-requested schedule can change.
  Published schedules remain protected by the existing amendment flow.
- Undo is client-side: each result returns the previous slot of every moved
  fixture, and `restore` puts them back through the same checks.

## Offline court app

Referees and club scorers score on their own phones, with their own portal
account, without a network at the venue.

**Who may score a match** is derived per match on every request:

- the head referee and assistant referees with a **confirmed** assignment and a
  linked user account (`federation.referee.user_id`);
- an optional **club scorer** that a club representative of one of the two
  clubs nominates on **My court duties** (`federation.match.scorer`); the
  nominee must be a club representative with a portal account;
- named court operators of the match's court.

Cancelling or replacing an assignment, or withdrawing a nomination, removes the
rights immediately: the next request from that phone is refused for the match.

**Preparing a phone.** On `/my/court-duties` (logged in, online) the scorer
chooses **Prepare this phone** for a game day. The server creates a
`federation.court.device` with a one-time code (10 minutes) and redirects to
`/court/app#code=…`; the fragment is never sent to a server. The app exchanges
the code for a random token and stores it. Only a SHA-256 hash of the token is
stored on the server. The token is valid for one game day (until the end of
the following day) and can be revoked by the scorer (**Remove**) or by a
match-day manager (**Scoring Phones > Revoke**).

**The app** is plain JavaScript in `static/court_app/` with its own page
(`/court/app`), service worker (`/court/sw.js`, scope `/court/`) and web app
manifest. The service worker stores the app files under a content-hashed
version; a new release activates only when no change is waiting and no match
is open. Data lives in IndexedDB (`sf-court`): the game-day pack, one journal
per match and the token. The app asks the browser to keep this data
(`navigator.storage.persist()`) and shows **Not ready offline** when the pack,
the stored app or persistent storage is missing (iPhones in particular may
refuse). After the game day the app deletes its data once everything is sent.

**The pack** (`POST /court/api/pack`) contains only the matches the user may
score: teams, court, times, officials, scoring rules (mode, set target, points
per won and drawn set) and the game-day line-ups with names, shirt numbers,
captain and crossed-out players. No birth dates, contact details or licences.

**Sync** (`POST /court/api/sync`) sends queued commands per match in order:

- `save`, `undo`, `submit`: the existing capture commands with idempotency key,
  expected revision and the *device signature* (match context without the
  match-day session, so a pack can be downloaded before the session opens);
- `participation`: the complete crossed-out list per line-up;
- `log`: the complete list of cards (blue, yellow, red; team and staff),
  time-outs and challenges.

The match-day session must be open to sync; changes stay on the phone until it
is. Only one phone scores a match: the first phone that syncs claims it, and
another phone must **Take over** explicitly (`/court/api/claim`, recorded as a
`handover` receipt). A refused change becomes a conflict on the phone: scores
are never merged; the scorer exports them and either takes over or keeps the
server version. Refusals are counted on the capture (`conflict_count`).

**Referee confirmation.** When the head referee scores, submitting confirms the
result. When someone else scores, the head referee can enter the PIN they set
on My court duties (4-6 digits, PBKDF2-hashed, locked for 15 minutes after 5
wrong attempts). A missing or wrong PIN never blocks the submission: the result
is marked *not confirmed by the head referee*. The PIN is not part of the
receipt digest and leaves the phone with the submission.

**Approval.** A court result never auto-approves, whatever the competition's
review flags: it stays *submitted* until the tournament manager clicks
**Approve Result** (one step: verify and approve by the same approver; the
submitter can never approve their own result). The match form shows a **Court
evidence** tab: set points per set, totals, outcome, crossed-out players, cards,
time-outs and challenges, who scored on which phone (and whether a club scorer
belongs to the home or away club), the referee confirmation, conflicts and all
receipts.

**Limits.** Rate limits per address: activation 10/min, pack 120/min, sync
600/min (`sports_federation.rate_limit.court_*`). Backend court-app journals
still on the phone (localStorage) are moved into the offline app and sent with
their original keys. Logic shared with the server is checked by
`ci/test_court_app_logic.py` and `ci/js/test_court_app.mjs` against
`ci/fixtures/court_scoring_cases.json`.

## Printing a game day

The game-day form has **Print schedule** and **Print score sheets** once the
game day has a live publication. The schedule is one landscape page to pin at
the venue: courts across, start times (event time zone) down, each match with
its division, teams and officials, followed by the club duties per club. A
match moved on the day prints on its operational court and time. **Print score
sheets** prints the existing score sheet of every published match in schedule
order as one PDF.
