# Copilot instructions

Odoo 19 addons for a sports federation (clubs, teams, seasons, competitions,
game days, officiating, rosters, results, standings, portal, public site,
reporting). Addons live at the repository root as `sports_federation_<domain>`.
`sports_federation_app` is the single installation entry point.

## Read first

- [Documentation map](../docs/README.md): where every subject is documented.
- [Architecture overview](../docs/architecture/overview.md) and
  [technical reference](../docs/architecture/technical-reference.md): structure,
  conventions, security and performance rules.
- [Competition model](../docs/architecture/competition-model.md): competition
  records, owners and handoffs.
- [Workflows](../docs/workflows/README.md): the authoritative business
  behaviour. Consult the matching workflow before changing a state, rule or
  operator journey, and ask which workflow governs a change when unclear.
- The addon's own `README.md`.

## Conventions

- Domain models use the `federation.` prefix. Lifecycle uses `state` selection
  fields with one explicit command per protected transition; never write
  `state` directly from controllers, wizards or other addons.
- Algorithms go in `services/`, interactive preview-and-confirm flows in
  `wizards/`, HTTP endpoints in thin `controllers/`.
- Put behaviour in the addon that owns the record. Import only from declared
  dependencies and reference other addons' models through the ORM.
- Portal writes go through `federation.portal.privilege` after resolving the
  user's club or team scope; public reads enforce publication flags. Any new
  elevated (`sudo()`) call must be inventoried in
  `ci/contracts/portal_sudo_inventory.json`.
- Published schedules, approved results and audit evidence are immutable;
  corrections use linked replacements.
- Odoo 19 groups use `privilege_id`, not `category_id`.

## When implementing a change

Return one patch that includes, as applicable:

- the model change and its `models/__init__.py` export;
- `security/ir.model.access.csv` rows and record rules for new models;
- views registered in `__manifest__.py` `data`, correct `depends`, and a
  `version` bump when an upgrade is needed;
- a focused, deterministic test under `tests/`, tagged for suite selection;
- documentation in the same change, following the
  [documentation map](../docs/README.md#where-new-information-belongs): addon
  README, the matching workflow, routes, menus, and an entry in the
  [upgrade notes](../docs/operations/upgrade-notes.md) for model, view or
  controller changes.

Keep changes minimal and inside module boundaries; explain any change to an
unrelated addon. Describe the current system in documentation, not the
delivery (no patch notes, validation logs or numbered phases).

## Checks

```bash
bash ./ci/run_tests.sh --module sports_federation_<name>
python3 ci/check_addon_integrity.py
python3 ci/check_workflow_state_contracts.py
python3 ci/check_migration_review.py --base-ref origin/main
python3 ci/check_markdown_links.py
python3 ci/check_doc_freshness.py
```

The full list is in [CONTRIBUTING.md](../CONTRIBUTING.md#before-pushing).
