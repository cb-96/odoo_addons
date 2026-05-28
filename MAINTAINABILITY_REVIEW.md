# MAINTAINABILITY REVIEW — 2026-04-19

Owner: Federation Platform Team
Last reviewed: 2026-04-19
Review cadence: Every release

This document records a module-by-module maintainability review of the current
codebase. It complements CODE_REVIEW_REPORT.md by focusing narrowly on
complexity concentration, module boundaries, review friction, upgrade safety,
and the lessons learned that should be checked in future reviews.

## Scope

- Review focus: maintainability only.
- Review method: static review of current addon structure, current hotspot
  files, current controller and public-route surface, current tests, current
  migrations, and current reuse patterns.
- Evidence sources: current addon code, MODULE_OWNERS.yaml, CODE_REVIEW_REPORT.md,
  and repository-local maintainability lessons already captured during prior
  work.

## Review Rubric

Each module was reviewed against the same questions:

- Is the module boundary still coherent, or is it absorbing too many concerns?
- Are the largest files still cohesive enough to review comfortably?
- Are controllers thin, or are they mixing access, orchestration, and writes?
- Are shared rules living in services or duplicated across models and templates?
- Does test shape follow the risk shape, or is one large file carrying too much?
- Are route, template, or schema changes likely to be upgrade-sensitive?
- Are risky patterns such as broad exception handling, public routes, or raw
  privilege escalation centralized and testable?

## Highest-Risk Modules

1. sports_federation_import_tools
Reason: giant transport and import hotspot files, public CSRF-disabled routes,
and broad exception handling in reusable flows.

2. sports_federation_portal
Reason: broad controller surface, large portal helper models, and very large
QWeb workflow templates.

3. sports_federation_public_site
Reason: one large public-flags model, one large public controller, many public
routes, and large website templates.

4. sports_federation_rosters
Reason: roster and match-sheet workflow logic is concentrated in two very large
model files.

5. sports_federation_reporting
Reason: SQL views have improved, but report scheduling and rendering orchestration
are still concentrated in one large model.

## Module Review

### sports_federation_base

Risk: Low

Signals:
- 20 Python files
- 8 XML files
- 6 test files
- 0 controllers
- 18 sudo() usages

Maintainability notes:
- attachment_policy.py, request_rate_limit.py, and failure_feedback.py are strong
  centralization points. Shared policy lives in the right addon instead of being
  duplicated downstream.
- test_base.py has become a broad umbrella file. It still works, but it is the
  first place where unrelated base behavior will start to pile up.
- The main maintainability risk is downstream coupling: changes here can look
  small locally but create cross-repo contract churn.

Lessons learned / checks:
- Add shared upload, rate-limit, and operator-feedback behavior here rather than
  rebuilding it in feature addons.
- Split test_base.py when one test file stops reflecting one coherent concern.
- Treat changes in base models and helpers as downstream API changes for many
  modules, even when there is no controller surface.

### sports_federation_competition_engine

Risk: Low

Signals:
- 19 Python files
- 5 XML files
- 9 test files
- 0 controllers
- 0 sudo() usages

Maintainability notes:
- services/round_robin.py and services/knockout.py keep scheduling and bracket
  generation out of models, which is the cleanest service boundary in the repo.
- stage_progression.py keeps advancement logic outside tournament core models.
- Tests are appropriately aligned with the algorithmic risk surface.

Lessons learned / checks:
- Keep pairing and bracket generation in services, not wizards or models.
- Add regression tests before changing bye handling, seeding, or bracket source
  wiring.
- If schedule options keep growing, split pairing generation from persistence and
  time assignment.

### sports_federation_compliance

Risk: Medium

Signals:
- 13 Python files
- 6 XML files
- 5 test files
- 2 controllers
- 8 sudo() usages

Maintainability notes:
- document_submission.py remains the main hotspot because it owns attachment
  validation, expiry semantics, portal submission flow, and recomputation side
  effects.
- document_requirement.py is dense but cohesive: workspace state and summary
  building are in one place.
- compliance_target_mixin.py is a strong extraction that reduces target-model
  drift across the addon.
- The controller layer is thinner than the model layer, but portal templates are
  already large enough to become a future friction point.

Lessons learned / checks:
- Add new target-model behavior through compliance_target_mixin.py, not through
  repeated per-model maps.
- Extract attachment and portal workflow services before document_submission.py
  grows further.
- Preserve explicit multipart/CSRF handling patterns in portal flows when file
  uploads are involved.
- Review upgrade impact whenever target maps, target field names, or portal URLs
  change.

### sports_federation_demo

Risk: Medium

Signals:
- 4 Python files
- 1 XML file
- 2 test files
- 0 controllers
- 0 sudo() usages

Maintainability notes:
- Almost all of the module lives in one scenario fixture file:
  demo/demo_federation_data.xml.
- test_demo_data_pack.py is the right counterweight because it validates model
  names, field names, XML refs, record counts, and the scenario shape.
- The module is easy to understand, but fixture drift will show up quickly if
  runtime schemas keep moving.

Lessons learned / checks:
- Keep this addon scenario-driven instead of turning it into a generic fixture
  dump.
- Split demo XML when new walkthroughs stop fitting the same narrative.
- Update the validation test in the same branch as any schema or seed-data change.

### sports_federation_discipline

Risk: Low

Signals:
- 11 Python files
- 9 XML files
- 4 test files
- 0 controllers
- 0 sudo() usages

Maintainability notes:
- The module stays compact and model-centric.
- disciplinary_case.py is readable and still behaves like a clear state machine.
- The risk is not code sprawl; it is limited depth in the current test shape if
  more cross-module integration gets added later.

Lessons learned / checks:
- Keep discipline workflow logic in dedicated models instead of leaking it into
  portal or finance addons.
- Add cross-module tests before adding more notification, finance, or reporting
  hooks.
- Introduce shared workflow constants if state semantics spread beyond the current
  few models.

### sports_federation_finance_bridge

Risk: Medium

Signals:
- 17 Python files
- 4 XML files
- 9 test files
- 0 controllers
- 3 sudo() usages

Maintainability notes:
- finance_event.py is still the main hotspot because one model owns lifecycle,
  export batching, serialization, and cursor handling.
- The hook files are a maintainability strength: trigger-specific behavior stays
  split by domain instead of collapsing back into one model.
- The test surface is broad and aligned with the hook model layout.

Lessons learned / checks:
- Keep new trigger logic in dedicated hook files, not in finance_event.py.
- Extract export cursor and serialization helpers before finance_event.py grows
  further.
- Preserve idempotent source linkage and explicit export state transitions.
- Add migration review whenever export lifecycle fields or handoff contracts change.

### sports_federation_governance

Risk: Low

Signals:
- 10 Python files
- 6 XML files
- 4 test files
- 0 controllers
- 0 sudo() usages

Maintainability notes:
- workflow_states.py is a healthy extraction that keeps state values and helpers
  out of individual models.
- override_request.py remains compact and restrained.
- The module does not currently absorb unrelated governance-adjacent behavior.

Lessons learned / checks:
- Keep workflow constants centralized in workflow_states.py.
- If override execution starts mutating target records directly, extract executors
  instead of expanding request models.
- Treat shared state-value changes as upgrade-sensitive because reporting and
  audit surfaces can depend on them.

### sports_federation_import_tools

Risk: High

Signals:
- 24 Python files
- 7 XML files
- 5 test files
- 2 controllers
- 22 sudo() usages
- 3 public routes
- 2 broad exception handlers
- 1 migration file

Maintainability notes:
- The former integration_gateway.py hotspot has now been split into
  integration_contract.py, integration_partner.py,
  integration_partner_contract.py, and integration_delivery.py, which removes
  the worst file-level concentration without changing the runtime surface.
- integration_partner.py now composes dedicated token-storage and
  rotation/audit helper mixins, so partner identity and subscription logic are
  no longer bundled with hashing and one-time token issuance details.
- integration_delivery.py now composes dedicated staging, workflow, and
  retention helper mixins so payload handling and lifecycle transitions are no
  longer stacked in one file.
- integration_api.py now composes dedicated auth and response helper mixins, so
  header parsing, rate-limit subject calculation, and typed JSON error shaping
  are centralized outside the route methods.
- import_wizard_mixin.py now composes dedicated CSV and governance helper
  mixins, which narrows the remaining hotspot to a stable composition surface
  instead of one grab-bag implementation file.
- integration_api.py is a meaningful long-term maintenance burden because it owns
  a public, CSRF-disabled integration surface.
- import_governance.py is a healthy counterexample: approval workflow is already
  kept distinct from transport handling.

Lessons learned / checks:
- Keep the per-model split intact and do not collapse contract, partner,
  subscription, and delivery behavior back into a gateway grab-bag file.
- Keep token storage, verification, and manager rotation behavior separated
  from partner identity and subscription lookup.
- Keep delivery staging, workflow transitions, and retention cleanup separated
  so future changes do not re-concentrate around one model file.
- Keep header parsing, rate-limit subject derivation, and typed JSON error
  payloads centralized in controller helpers instead of duplicating them in
  each route.
- Keep CSV parsing/error taxonomy separate from governance/result persistence in
  shared import wizards.
- Narrow broad exception handling in reusable import and HTTP layers.
- Separate inbound staging from attachment persistence and retention policy.
- Keep authentication header-only and do not reintroduce query-string fallback.
- Require migration handling for token storage, delivery state, and governance-job
  changes.

### sports_federation_notifications

Risk: Medium

Signals:
- 11 Python files
- 4 XML files
- 5 test files
- 0 controllers
- 11 sudo() usages
- 4 broad exception handlers
- 1 migration file

Maintainability notes:
- notification_dispatcher.py has become a growing event matrix across many
  business domains.
- notification_service.py is a good generic boundary, but broad exception
  handling still hides failure categories.
- Mail template XML is a significant behavior contract and should be reviewed as
  code, not as passive content.

Lessons learned / checks:
- Keep generic sending separate from domain-specific dispatch methods.
- Add a trigger test and template assertion whenever a new dispatcher method lands.
- Narrow exception categories so transport failures, misconfiguration, and
  developer defects are distinguishable.
- Split dispatcher behavior by domain once event count keeps climbing.

### sports_federation_officiating

Risk: Low

Signals:
- 8 Python files
- 5 XML files
- 4 test files
- 0 controllers
- 0 sudo() usages

Maintainability notes:
- federation_match_referee.py is the one meaningful hotspot because it combines
  referee assignment logic and a federation.match extension.
- The addon stays controller-free, which keeps maintenance simpler.
- Tests are focused and proportionate to the surface area.

Lessons learned / checks:
- Split assignment and match-extension logic if officiating rules expand much more.
- Keep notification dependencies optional through env lookups.
- Add focused tests before introducing more staffing or certification rules.

### sports_federation_people

Risk: Low

Signals:
- 7 Python files
- 4 XML files
- 2 test files
- 0 controllers
- 0 sudo() usages

Maintainability notes:
- Player and player-license behavior are separated cleanly.
- The module is intentionally small and readable.
- The main future risk is compatibility cleanup, not architecture drift.

Lessons learned / checks:
- Keep this addon limited to person and license master data.
- Add more focused tests only if license lifecycle rules become materially richer.
- Remove compatibility shims once the version baseline is stable and the cleanup
  can be done safely.

### sports_federation_portal

Risk: High

Signals:
- 40 Python files
- 20 XML files
- 14 test files
- 12 controllers
- 52 sudo() usages
- 1 public route

Maintainability notes:
- portal_privilege.py is the strongest maintainability improvement on the portal
  surface because privilege escalation and audit behavior are centralized.
- federation_team_roster.py is still a large helper hotspot with many portal-only
  methods for scope, access, creation, and state transitions.
- The controller surface remains broad across roster, match-day, registration,
  officiating, and auth flows.
- portal_roster_templates.xml and portal_templates.xml are large QWeb hotspots and
  now carry accessibility and mobile review pressure as well.
- Test shape is strong and matches the risk surface better than most addons.

Lessons learned / checks:
- Keep ownership and elevation checks in model helpers or portal_privilege.py,
  not in controllers.
- Split giant template files by workflow area before adding more portal pages.
- Avoid direct controller writes through raw sudo outside the privilege boundary.
- Treat route and template-anchor changes as upgrade-sensitive.
- Watch repeated controller query and redirect patterns for the next extraction pass.

### sports_federation_public_site

Risk: High

Signals:
- 17 Python files
- 9 XML files
- 8 test files
- 3 controllers
- 59 sudo() usages
- 20 public routes
- 2 migration files

Maintainability notes:
- public_flags.py is the biggest hotspot in the public surface: slugging,
  publication rules, bracket assembly, schedule access, results access, feeds,
  and ICS generation are all concentrated there.
- public_competitions.py is a second hotspot because page rendering, redirects,
  filters, public API responses, and registration POST flows are mixed together.
- website_hub_templates.xml and website_templates.xml are large and brittle enough
  to deserve continuous upgrade attention.
- The module has strong API and route tests, plus explicit migrations for website
  cleanup and compatibility.

Lessons learned / checks:
- Split public_flags.py by entity or concern before adding more helpers.
- Separate API/feed endpoints from page controllers.
- Keep rate limiting centralized in the base addon.
- Preserve migration discipline for website menus, footer cleanup, and inherited
  templates.
- Review every new public or CSRF-disabled route as a long-lived maintenance cost.

### sports_federation_reporting

Risk: High

Signals:
- 28 Python files
- 13 XML files
- 8 test files
- 2 controllers
- 1 sudo() usage
- 1 broad exception handler
- 1 migration file

Maintainability notes:
- report_schedule.py is the main bottleneck: report builder selection, rendering,
  persistence, failure typing, cron behavior, and retention cleanup are still in
  one file.
- The SQL view side is materially healthier than before because it is already
  split into multiple focused model files.
- test_operational_reporting.py is useful but monolithic because it mirrors the
  breadth of the scheduling layer.

Lessons learned / checks:
- Add a builder registry or report service layer before any new report type lands
  in report_schedule.py.
- Keep per-report SQL views separate and resist re-centralizing them.
- Preserve query-budget tests when changing builders or heavy SQL views.
- Treat upstream addon field changes as reporting contract changes.
- Keep migrations and backfills for changes to failure metadata or stored report
  payload behavior.

### sports_federation_result_control

Risk: Low

Signals:
- 7 Python files
- 2 XML files
- 4 test files
- 0 controllers
- 1 sudo() usage

Maintainability notes:
- match_result_control.py is still an understandable, explicit workflow hub.
- Audit rows are kept separate from transition logic.
- The module is small and stays within its domain.

Lessons learned / checks:
- Keep result lifecycle rules centralized here, not duplicated in portal or
  standings code.
- Preserve role separation between submitter, verifier, and approver behavior.
- Add migration review if result states or audit fields change.

### sports_federation_rosters

Risk: High

Signals:
- 14 Python files
- 7 XML files
- 7 test files
- 0 controllers
- 0 sudo() usages

Maintainability notes:
- team_roster.py is the single largest maintainability hotspot in the repo.
- match_sheet.py is a second large workflow-heavy file, so the module’s logic is
  concentrated in two places rather than distributed by concern.
- The test surface is strong and clearly tied to invariants such as readiness,
  eligibility, and match-sheet behavior.

Lessons learned / checks:
- Split team_roster.py into roster, roster-line, and helper files before adding
  more features.
- Extract readiness, eligibility, and audit helpers instead of extending model
  methods indefinitely.
- Keep match-day lock invariants covered with end-to-end tests.
- Coordinate with portal behavior, but keep portal-only logic out of this addon.
- Add migration planning for uniqueness, lock, or eligibility field changes.

### sports_federation_rules

Risk: Low

Signals:
- 16 Python files
- 8 XML files
- 4 test files
- 0 controllers
- 0 sudo() usages

Maintainability notes:
- services/eligibility.py is the main hotspot, but it is the right kind of
  hotspot because it keeps rule evaluation out of feature addons.
- Rule models are comparatively small and focused.
- Tests are deep and aligned with the main service boundary.

Lessons learned / checks:
- Keep rule evaluation in services, not in consuming modules.
- Replace large rule-type if-chains with pluggable handlers before the next large
  rule-set expansion.
- Maintain deep tests for every new rule type or context key.

### sports_federation_standings

Risk: Medium

Signals:
- 9 Python files
- 3 XML files
- 8 test files
- 0 controllers
- 0 sudo() usages

Maintainability notes:
- standing.py is a large but cohesive computation hub.
- Integration with result-control remains optional and explicitly tested.
- There is no controller surface in the addon itself, which helps contain change.

Lessons learned / checks:
- Extract ranking or tie-break strategies if rule variation keeps increasing.
- Keep optional result-control integration explicitly tested.
- Watch performance before moving more aggregation into Python loops.

### sports_federation_tournament

Risk: Medium

Signals:
- 14 Python files
- 10 XML files
- 4 test files
- 0 controllers
- 0 sudo() usages

Maintainability notes:
- federation_match.py is a large hotspot because it owns schedule normalization,
  bracket linkage, source-match behavior, and state.
- federation_tournament.py carries state transitions, rule-set inheritance, and
  team-selection behavior.
- The rest of the domain remains reasonably well factored across rounds, groups,
  stages, participants, competitions, and editions.

Lessons learned / checks:
- Keep match, tournament, participant, and stage responsibilities split.
- Add more focused tests if bracket and source-match behavior grows richer.
- Treat field changes here as downstream API changes for many dependent addons.

### sports_federation_venues

Risk: Low

Signals:
- 10 Python files
- 5 XML files
- 6 test files
- 0 controllers
- 0 sudo() usages

Maintainability notes:
- federation_match_inherit.py confines round and venue defaults cleanly.
- venue.py remains narrow and separate from schedule orchestration.
- Tests are targeted and proportionate to the surface area.

Lessons learned / checks:
- Keep scheduling orchestration in the competition engine, not here.
- Keep finance and public-site venue behavior in those addons instead of widening
  this module.
- Add tests whenever round defaults or playing-area constraints change.
