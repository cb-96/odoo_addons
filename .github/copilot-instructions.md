**Repository Summary**
- **Purpose**: Odoo 19 custom addons to manage a sports federation (clubs, teams, seasons, tournaments, rules, officiating, rosters, results, public site, reporting).
- **Location**: All addons live under the `odoo/` folder as individual modules prefixed with `sports_federation_`.
-- **Primary docs**: See [odoo/CONTEXT.md](odoo/CONTEXT.md#L1), [odoo/TECHNICAL_NOTE.md](odoo/TECHNICAL_NOTE.md#L1), and the Workflows in [odoo/_workflows/WORKFLOW_TOURNAMENT_LIFECYCLE.md](odoo/_workflows/WORKFLOW_TOURNAMENT_LIFECYCLE.md#L1).

**Architecture & Patterns**
- **Module split**: `sports_federation_base` (master data), `sports_federation_tournament` (tournaments, matches, participants), `sports_federation_format / sports_federation_scheduling` (service/wizards), plus domain modules (`people`, `rules`, `officiating`, `rosters`, `result_control`, `public_site`, `reporting`, `finance_bridge`, `venues`, `discipline`, `standings`, ...).
- **Model naming**: Domain models use the `federation.` prefix (e.g. `federation.player`, `federation.match`).
- **Common patterns**: `ir.sequence` for identifiers, `state` selection fields for workflows, wizards for batch operations (under `wizards/`), `controllers/` for portal/website endpoints, and `security/` for groups/record rules/ACLs.

**Key Files & Where To Look**
- **High-level context**: [odoo/CONTEXT.md](odoo/CONTEXT.md#L1)
- **Technical architecture**: [odoo/TECHNICAL_NOTE.md](odoo/TECHNICAL_NOTE.md#L1)
-- **Workflows (authoritative behavioural spec)**: [odoo/_workflows/WORKFLOW_TOURNAMENT_LIFECYCLE.md](odoo/_workflows/WORKFLOW_TOURNAMENT_LIFECYCLE.md#L1) and the other files inside `odoo/_workflows`.
- **Module READMEs**: each module may have a `README.md` under `odoo/<module>/README.md` with implementation notes and expectations.
-- **Install logs / historical notes**: `_logs/` contains installation and setup notes per module.

**Development Guidelines (how to implement changes)**
- **Add/modify a model**: create/modify `models/*.py`, export package in `models/__init__.py`, add access rules in `security/ir.model.access.csv`, add any initial `data/*.xml` and register them in `__manifest__.py` `data` or `demo` lists, add views in `views/*.xml`, update `menu_items.xml` as needed, and add tests under `tests/`.
- **Add a wizard or service**: put transient models under `wizards/` and views under `views/` (manifest `data`), keep service logic in modules like `sports_federation_format / sports_federation_scheduling` (no persistent models if not required).
- **Add a controller / portal flow**: use `controllers/` and add templates under `views/` or `templates/`; respect portal record rules (see `sports_federation_portal`).
- **Security**: always add or update `security/ir.model.access.csv` and any `security/*.xml` groups/rules for new models or new endpoints.
- **Manifest hygiene**: update `__manifest__.py` `depends`, `data`, and `version` fields when introducing DB changes or new data files.

**Testing & Local Run**
- **Where tests live**: `odoo/<module>/tests/` when present (some modules include unit/functional tests).
- **Run module tests**: use the Odoo test runner for module-level tests (e.g. `odoo-bin -d <db> -i <module> --test-enable`) or your established local development workflow.
- **Release sanity**: include at least one focused test for new business logic (especially schedule generation, result pipeline, and state transitions).

**PR Checklist (required before merge)**
- **Tests**: Add/adjust tests covering the new behaviour.
- **Security**: Update `security/ir.model.access.csv` and add group/record-rule XML if necessary.
- **Manifest**: Add new data files to `__manifest__.py` `data` list and ensure `depends` are correct.
-- **Docs**: Update or add a short README in the module and, if behaviour changes, update the relevant `odoo/_workflows` file.
- **Small, focused commits**: Prefer atomic commits (one logical change per commit) and descriptive commit messages.

**How Copilot Should Help (recommended prompts & behaviour)**
- **Primary rule**: Prefer conservative, minimal changes that keep module boundaries intact. Avoid touching unrelated modules unless absolutely required and explain why.
- **When asked to implement a model change**: return a plan and a single patch that includes: the `models/<file>.py` change, `models/__init__.py` export, `security/ir.model.access.csv` entry, `views/*.xml` (if UI), `__manifest__.py` update, and a new test under `tests/` that exercises the main logic.
- **When asked to add a wizard or generator**: create a transient model in `wizards/`, a wizard view, and a small deterministic example in tests that demonstrates expected output (e.g. round-robin schedule for 4 participants).
- **When asked about business rules or workflows**: consult and reference the Workflow docs in `odoo/_workflows` and the `TECHNICAL_NOTE.md` to ensure behaviour matches the documented flows.

**Example prompts you can give Copilot in this repo**
- **Add a model**: "Add a new persistent model `federation.referee` with fields `name`, `certification_level`, `active`; add ACLs, a basic tree/form view, and unit tests. Show me the patch with files changed."
- **Create a wizard**: "Create a `round_robin_wizard` that generates matches for a stage; include wizard model, view, manifest update, and a unit test verifying match count for 4 teams."
- **Fix workflow behaviour**: "Investigate why standings recompute includes contested results; propose a minimal fix and tests to prevent contested results from being counted."

**Notes & Expectations**
- **Authoritative sources**: the `_workflows` documents and `TECHNICAL_NOTE.md` are the source of truth for business behaviour—use them before changing workflows.
- **Keep modules decoupled**: the architecture intentionally separates `base`, `tournament`, and the `competition_engine` service; prefer adding features in the appropriate module.
- **Ask clarifying questions**: if a requested feature impacts tournament rules, scheduling, or publication flows, ask which workflow (`_workflows/*.md`) should govern the behaviour.

**Documentation Maintenance (required)**

- **Always update docs**: For any code, data model, view, workflow, or behaviour change, update the relevant documentation files in this repository as part of the same change set (or in a linked follow-up PR). At minimum, consider updating `odoo/TECHNICAL_NOTE.md`, `odoo/CONTEXT.md`, the module-level `README.md` under the affected `odoo/<module>/`, and any affected workflow files under `odoo/_workflows/`.
- **Doc scope**: Document API/ORM changes, new models, new fields, migration notes (DB changes), public website impacts, and any user-facing behaviour changes. Include brief examples or CLI commands for running tests or sample data when useful.
- **PR checklist enforcement**: Fail-fast — do not open a PR merging code that introduces behavioural or schema changes without documentation entries. If you cannot edit docs yourself (e.g., lacking domain clarity), leave a clear TODO in the code and notify repository maintainers.
- **Why**: Keeping documentation current ensures maintainability, reduces onboarding friction, and prevents accidental regressions in workflows that rely on textual contracts (workflows, assumptions, and operational steps).

