# Competition workflow

Owner: Federation Competition Operations
Last reviewed: 2026-11-06
Review cadence: Every release

How an organiser runs a competition in the back office, from creation to
finish. The business rules behind each step are in the
[tournament lifecycle](../workflows/tournament-lifecycle.md) and the other
[workflows](../workflows/README.md); format choices are explained in
[competition formats](competition-formats.md).

## Canonical entry

Use one backend path for creating, resuming and operating a competition:

```text
Federation > Competitions > Competitions
```

The list disables raw season-edition creation. **Create Competition** opens the governed creation wizard; **Open Workspace** (or **Open Competition Hub** on the competition form) opens the Competition Hub. The hub projects the same readiness result used by the edition form, promotes exactly one next action, and retains the active competition scope when it opens an owning domain action.

Direct model actions and specialist menus still exist for contextual deep links, recovery, advanced operation, compliance, audit and security. Users assigned **Advanced Federation Tools** can reach them from the hub or the advanced menu paths in [backend navigation](backend-navigation.md).

## Simplified end-to-end journey

### 1. Create with a meaningful preset

Choose **Create Competition** from **Federation > Competitions > Competitions**. Presets supply editable defaults:

- **Season League**: multi-day division, league format, streamlined workflow, season-aligned end date, and a 30-day registration lead.
- **One-Day Tournament**: single-day division, league format, streamlined workflow, and same-day start/end.
- **Knockout Cup**: multi-day division, knockout format, independent review, and an eight-week planning window.
- **Custom**: leaves advanced choices to the operator.

The wizard also remembers the default venue, day start/end, and match-slot duration on the season competition. These values seed the resumed planning steps instead of being discarded after creation.

Workflow language is operator-facing:

- **Streamlined**: one operator may complete routine checkpoints after all validations pass. Registration, schedule review/publication, game-day lineup approval, and result verification/approval still execute their existing commands, snapshots, and audit events.
- **Independent Review**: another responsible person approves protected work.
- **Advanced / Custom**: an advanced user configures individual checkpoints.

Changing the selected season resets a start date only when that date falls
outside the new season; dates already inside the season remain editable. The
additional responsibility rows assign roles only within this competition.
Per-competition assignments do not grant model access, so each operator also
needs the matching federation-wide access group in user settings: Federation User is the base; Registration
Manager controls team and participant setup, Calendar Planner controls game
days, Schedule Planner controls working schedules, and Schedule Approver
enables independent review. A person working across areas may need more than
one group. Competition Designers can read finalized participant sets for
format setup, but only Registration Managers can change those records.

### 2. Select teams directly

The next action opens **Select Teams** for the first incomplete division. Operators select eligible active teams directly; the command automatically materializes the existing registration window, approved entries, seeds, and finalized participant set.

This does not replace registration models. It is a simplified command over them. Repeating the same selection is idempotent. Once a finalized participant set feeds a format, the picker refuses to rewrite history and directs the operator to the governed successor/version workflow.

Club self-service registration remains available in the portal and the advanced **Registration Desk**.

### 3. Choose the playing format

The next action opens **Choose Format** with the preset default:

- league, once;
- home-and-away league; or
- knockout cup.

The wizard creates or resumes the canonical competition structure, runs the existing feasibility and fixture-generation commands, and freezes the generated structure. Complex stage graphs remain in **Federation > Competitions > Advanced Competition Tools > Format Studio**.

### 4. Define game days and plan the schedule

**Define Game Days** opens as a dialog with its save/continue footer visible and starts with the remembered venue, hours, duration, and competition start date. Existing days are loaded for correction; recurring-day and copy-last-day helpers remain available.

**Save & Plan Schedule** opens the unified competition schedule wizard directly. The wizard selects current structures, stages, and game days, previews included/excluded fixtures and capacity, generates slots, allocates fixtures, creates working schedules, and auto-schedules through the owning domain commands. Applying from the workspace returns to the same workspace.

New game-day rows inherit active courts from the default venue, and their court
picker is restricted to that venue. Preview reports explain each day's fixture
count and capacity in readable tables. A fixture already allocated to another
day is excluded from a partial run; if the same fixture is already allocated to
multiple days, generation is blocked until the calendar is corrected. Generated
allocations retain the exact fixture subset assigned to each day.

Planner dead ends are removed:

- no game days → Define Game Days;
- unallocated fixtures with days → Plan Competition;
- missing schedule → Plan Competition;
- capacity/court blocker → Define Game Days;
- review/publication blocker → exact schedule or review record.

### 5. Review and publish

Submitting a schedule always creates the existing immutable review snapshot.

- In **Streamlined**, the command validates, records the review decision, and publishes automatically when no live publication would be replaced.
- In **Independent Review**, the workspace opens the exact pending review for another responsible user.
- Replacing a live publication still requires the amendment/replacement reason and preserves the superseded snapshot.

The Streamlined policy permits the submitting planner to complete its approval
command; Independent Review requires a different assigned approver. Both paths
retain immutable review evidence. Review and publication screens render the
snapshot as a match, fixture, court, and time table while keeping the original
JSON evidence intact. The publication note is optional on the first publish
and required only when replacing a live publication. A planner publication
blocker opens the pending or approved review for the current schedule revision
directly.

### 6. Prepare rosters and one game-day roster per team

Unified readiness includes roster and game-day roster work.

**Prepare Gameday Rosters** (on the game day) opens one form per team: choose
the active season roster, the players who come to that game day, the captain
and jersey numbers. The game-day roster is shared by every match the team
plays that day. No starters or substitutes are declared in advance; at each
match the coach crosses out the game-day players who do not play. Crossing out
is match-specific and never edits the game-day roster. Rule sets can limit the
game-day roster size and the number of players per match.

**Save & Submit Roster** validates the game-day roster. In Streamlined mode it
also records the approval automatically; Independent Review leaves it
submitted for another responsible person. **Save Draft** keeps it editable.

For senior participation, a player under 16 must have a verified parental
approval covering the participation date. The roster and match-sheet
eligibility services enforce this server-side. Missing approvals also appear
in the single `federation.operation.task` projection and open the player's
approval records directly.

### 7. Operate, record results, and publish standings

The Competition Hub projects the next operational action from the existing models:

1. roster readiness;
2. game-day roster preparation;
3. official coverage;
4. result follow-up; or
5. match-day operations when no blocker remains.

Result submission keeps deliberate score validation. Streamlined mode invokes the existing verification and approval commands automatically; Independent Review preserves separation of duties. Official standings and public publication continue to use their existing protected actions and immutable/audited records.

## One actionable task projection

The Competition Hub promotes one `primary_action` at a time and shows one unified readiness summary. The existing `federation.operation.task` model remains the sole persistent task projection for portal/backend follow-up. It now also projects:

- missing verified parental consent; and
- one game-day roster task per team and game day.

No second task model or parallel state machine is introduced. Source records remain authoritative, stale projections are completed, and direct source navigation is preserved.

## Recovery and advanced routing

From the Competition Hub, users with **Advanced Federation Tools** can open:

- **Advanced tools**: the former owner-module router and raw workspaces;
- **Administration**: the scoped action queue or operational job health;
- the exact source record for each readiness blocker.

Important recovery rules remain unchanged:

- correct mutable drafts in their owning workflow;
- create successor structures or schedule revisions after freeze/review;
- replace, never mutate, live schedule publications;
- correct approved results through the correction command;
- keep signed parental approvals, audit events, publication snapshots, and stage snapshots as evidence;
- do not bypass role checks, record rules, or server-side validation because a menu is hidden.

## Retained advanced paths

```text
Federation > Competitions > Advanced Competition Tools > Create Competition
Federation > Competitions > Advanced Competition Tools > Registration Desk
Federation > Competitions > Advanced Competition Tools > Format Studio
Federation > Competitions > Advanced Competition Tools > Calendar Planner
Federation > Competitions > Advanced Competition Tools > Schedule Planner
Federation > Competitions > Advanced Competition Tools > Schedule Review Queue
Federation > Administration > Competition Audit & Recovery > Role Assignments
Federation > Administration > Action Queue
Federation > Administration > System Health > Operational Job Health
```

These menus are intentionally absent from an ordinary manager’s navigation but their action XML IDs remain stable for bookmarks, contextual actions, tests, and integrations.
