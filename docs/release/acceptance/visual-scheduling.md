# Visual scheduling acceptance

Owner: Federation Competition Operations
Last reviewed: 2026-11-06
Review cadence: Every release

Acceptance scenarios for the visual schedule planner and progression impact
in `sports_federation_live_workspace`. The fairness solver, schedule
validator, immutable proposals, schedule commands, amendment workflow and
independent publication stay authoritative; the planner adds no alternative
scheduling engine and cannot edit published assignments.

## Behaviour under test


- Drag assigned or unassigned fixture buttons onto assessed court/time destinations.
- Equivalent fixture selection and slot activation using native controls, Enter/Space, Tab, arrows, Home and End.
- Textual destination states: not assessed, allowed, allowed with preference warning, current slot, blocked by a mandatory rule. Colour is supporting feedback, never the only distinction.
- Invalid slots remain inspectable. Selecting a blocked slot shows its mandatory explanation and a corrective hint without applying or silently swapping anything.
- Saved-preference and mandatory-rule summaries, conditional rule-entry fields, plain-language rule labels and resolution hints.
- Exact before/after slot changes, unallocated counts, fairness penalties and warnings.
- Candidate A/current comparison using two persisted, actor-owned previews from the same unchanged revision. Candidate selection does not apply it.
- Impact groups distinguish actual slot changes, shared-team rest/overlap review, explicit winner/loser dependencies and potential stage qualification dependencies.
- Stage cards show rank ranges, target stages, fixture source outcomes and fixture links. Relevant structures include all divisions allocated to the physical match day, not just the schedule's creation structure.
- Progression/topology changes invalidate previews. Impact never predicts winners, changes qualification, advances a stage or automatically moves downstream fixtures.
- Regeneration explicitly rejects unintended changes to manual/operational pins. Explicit reasoned moves can change a pin and show that fact.
- Constraint mutations, destination assessment, preview and application share the schedule lock. Existing command revision/signature checks remain in place.
- Applying remains a reasoned working-schedule change, not approval or publication. Published schedules use the existing guided amendment, linked replacement and independent review.

## Entry and ordinary journey


Open the existing schedule record and its Visual planning action. Existing setup/capacity generation remains the route for creating match days, slots and allocations.

1. Confirm participants, format/progression and court/time capacity through the existing competition setup flow.
2. Add mandatory team/court unavailable windows or mandatory minimum rest where needed. The minimum-rest rule applies to all teams; preferred rest is a separate soft setting.
3. Save fairness preferences before generating candidates. Unsaved preference fields are not used by the server preview.
4. Preview regeneration. Review missing allocations, mandatory errors, warnings, pins and weighted penalty. A heuristic failure is not proof of infeasibility.
5. Choose a fixture. Wait for destination assessment. Click or keyboard-activate a slot, or drag the selected fixture to it. Dropping only creates a preview.
6. Inspect the exact changed slots and review-impact groups. Enter a reason and apply exactly the selected preview.
7. Return to the canonical schedule record for complete-schedule checks, independent review and publication.

Missing allocations are not mandatory violations of a partial working edit, but they still block complete-schedule/publication readiness through the existing workflow. Destination assessment checks the entire candidate: an unrelated existing mandatory error is shown too. If several existing conflicts cannot be resolved with one valid move, use constrained regeneration or the existing canonical planning workflow rather than bypassing validation.

## Candidate comparison


Keep a preview as candidate A, then preview a different move or regeneration without applying, refreshing, changing rules or saving new preferences. Compare A with the current candidate. The comparison reports:
- Different fixture slots.
- Mandatory blocker counts.
- Preference-warning counts.
- Unallocated fixture counts.
- Weighted fairness penalty, where lower is better only among comparable feasible/complete candidates.

Use candidate A for application swaps the displayed selection, not the database schedule. The final apply command still checks the stored actor, candidate, reason, current signature and revision. Applied or stale proposals cannot be compared. Previews created before an upgrade that changes the signature logic are stale; regenerate them.

## Progression boundary


Actual slot changes are exact. Shared-team and downstream groups are review effects, not additional changes. A stage dependency may affect all fixtures in the downstream stage because the eventual qualifier is not yet known. Explicit fixture-source links identify winner/loser dependants more precisely. These groups may overlap, and are labelled separately.

Matches of later stages exist from the start as placeholders ("#1 Group A", "Winner R1 M2") and can be scheduled and published before their teams are known; see [Competition formats and stage planning](../../user-guide/competition-formats.md). The validator keeps a later stage after the stage that feeds it. Teams are filled in through the existing standings-freeze and governed progression workflow. Verify rest again when participants resolve.

## Automated validation

Runtime tests are tagged `sf_visual_scheduling` (ORM and browser cases); a Playwright staging smoke runner complements them. XML parsing is not proof of Owl/QWeb rendering or registry validity.

```bash
PYTHONDONTWRITEBYTECODE=1 python ci/static_checks.py
PYTHONDONTWRITEBYTECODE=1 python ci/test_visual_policy.py
PYTHONDONTWRITEBYTECODE=1 python ci/test_visual_acceptance.py
node ci/test_visual_helpers.mjs
node --check ci/visual_scheduling_browser.mjs
odoo-bin -d STAGING_TEST_DB -u sports_federation_live_workspace \
  --test-enable --test-tags sf_visual_scheduling,sf_live_workspace --stop-after-init
```

Also run existing scheduling, calendar, format/progression, amendment and publication tests, including installation and upgrade lanes. Run independent-transaction races for constraint changes, assignment changes and stale application. The added schedule lock does not substitute for concurrency qualification of every other domain command.

## Live browser smoke


The runner needs Playwright with Chromium, an authenticated staging organiser, a prepared working schedule and an existing client action whose context/params selects that schedule.

Set `SF_BASE_URL` and `SF_VISUAL_FIXTURES` through the test environment or secret store. Do not commit credentials. The JSON configuration requires:

- `login`, `password`.
- `action_id`: existing `federation_visual_plan` client action for the fixture schedule.
- `schedule_id`, `fixture_id`.
- `first_slot`, `second_slot`: two distinct valid destinations for the fixture.
- `blocked_slot`: a third destination blocked by a mandatory rule, not merely a preference warning.

Use a disposable match day with at least two courts, realistic constraints, available capacity and an initially assigned or assignable fixture. The runner applies one reasoned working move. It does not publish.

```bash
node ci/visual_scheduling_browser.mjs
```

It exercises native keyboard fixture/slot selection, invalid-slot explanation, candidate comparison, reasoned application, native drag preview and regeneration pin checks. Missing fixtures fail. This smoke is not the full human usability suite or proof of every hard constraint.

## Required staging scenarios


### Constrained multi-court generation

Prepare multiple teams, at least two courts, sufficient slots, a venue/court blackout, team-unavailable window, mandatory minimum rest and distinct preferred rest. Pin at least two assignments. Preview regeneration and compare every retained pin's fixture/slot/method before and after. Inspect unallocated fixtures and rejected-slot explanations. Apply only a candidate without mandatory errors, then run complete-schedule checks.

### Move and explain consequences

Select a fixture with a shared-team neighbour and downstream dependencies. Use keyboard and drag separately. Confirm both produce the same candidate map and neither applies immediately. Identify exact changed fixtures, shared-team review effects and downstream qualification/source effects. Check current/blocked/allowed labels without relying on colour. Verify occupied destinations never silently swap or overwrite fixtures.

### Resolve overlap and rest

Attempt a team overlap across courts: mandatory blocker and no accepted application. Attempt a preferred-rest shortfall without a mandatory-rest rule: preference warning, not a blocker. Add mandatory minimum rest and repeat: application must reject it. Resolve using a valid later slot or constrained regeneration. Check the recorded rule explanation and the before/after schedule.

### Compare two candidates

Keep candidate A, create B on the same revision, compare slots, mandatory errors, preference warnings, missing allocations and fairness penalty. Select A and apply it with a reason. Confirm B becomes stale after application. Repeat with another organiser's proposal and a changed constraint: reject foreign/stale comparison. A lower penalty must not be described as a valid complete schedule when fixtures are unallocated.

### Group-to-knockout progression

Use an existing pools-to-knockout or custom acyclic stage graph. Follow outgoing rank ranges to the target stage and explicit winner/loser fixture sources. Change a group fixture's slot and identify potential downstream review effects. Freeze standings and advance through the canonical progression action. Confirm resolved participants appear in the appropriate fixtures and old previews become stale. No slot move should advance or mutate progression itself.

### Amend a published schedule

Open the published visual workspace: direct destination editing and regeneration are unavailable. Record an amendment reason and create the guided replacement after closing live operations. Confirm the immutable publication snapshot is unchanged, assignments and constraints are copied to the linked replacement, and subsequent edits still require preview/application. Submit for independent review and publish through existing controls, not the visual apply button.

## Defined integrity suite


Record executed cases and accepted violations for each category:

`scope`, `unavailable_slot`, `venue_blackout`, `occupied_slot`, `team_overlap`, `mandatory_rest`, `unresolved_participants`, `stale_preview`, `published_immutability`, `pinned_regeneration`.

Include API calls as well as UI interactions. For each invalid candidate, confirm no assignment change, no unintended revision/business transition and no published snapshot mutation. For regeneration, compare every retained manual/operational pin and record `unintended_pin_changes`. Include a fixture from another allocated division on the same physical day to verify the multi-structure boundary.

## Human metrics


Recruit at least ten distinct novice organisers. Give the constrained planning goal without navigation coaching. Record participant pseudonym, unassisted completion, correct hard-versus-preference explanation and correct identification of affected fixtures. Record failures and assistance, not just successful users.

For planning time, use at least ten paired successful baseline/candidate runs of comparable constrained tasks. Counterbalance task order to reduce practice effects. Measure the same start/end boundary and workload. Do not substitute solver runtime for organiser planning time. The evaluator compares the median candidate time with the median baseline time; failed or missing runs cannot establish a timing improvement.

The evaluator expects real JSON observations with:
- `novices`: `participant`, `completed`, `assisted`, `hard_vs_preference_correct`, `affected_fixtures_correct`.
- `paired_timings`: `participant`, `baseline_completed`, `candidate_completed`, `baseline_seconds`, `candidate_seconds`.
- `integrity`: every category above with `executed` and `accepted_hard_violations`; `pinned_regeneration` also has `unintended_pin_changes`.

```bash
python ci/evaluate_visual_scheduling.py observations.json --output visual-acceptance.json
```

Missing evidence fails. Required gates: at least 80% unassisted novice completion, at least 90% hard/preference understanding, at least 90% affected-fixture identification, median planning time improvement at least 30%, zero accepted hard violations and zero unintended pin changes.

## Operational checks before rollout


Test real browser drag behaviour, keyboard focus and screen-reader announcements. Validate narrow screens even though this planning workspace is primarily an organiser tool. Test large multi-court schedules: destination assessment evaluates a full candidate per slot and may require performance tuning at your scale. Monitor query count, request duration and lock contention. Existing access rules, source-domain mutability and independent review remain authoritative.
