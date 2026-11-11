# Documentation

Owner: Federation Platform Team
Last reviewed: 2026-11-06
Review cadence: Every release

This is the single map of the repository documentation. Every subject has one
home. When you need to write something down, find its home in the table below
and update that file instead of creating a new one.

## Find what you need

| I want to… | Read |
| --- | --- |
| Understand what the product does | [Product overview](overview/product.md) |
| Find which addon owns something | [Module catalogue](overview/modules.md) |
| Look up a term (edition, division, game day…) | [Glossary](overview/glossary.md) |
| Run a competition in the back office | [Competition workflow](user-guide/competition-workflow.md) |
| Find a menu | [Backend navigation](user-guide/backend-navigation.md) |
| Set up a league, cup or custom format | [Competition formats](user-guide/competition-formats.md) |
| Follow a business process step by step | [Workflows](workflows/README.md) |
| Understand the architecture | [Architecture overview](architecture/overview.md) |
| Check implementation conventions and patterns | [Technical reference](architecture/technical-reference.md) |
| See which record owns which state | [State and ownership](architecture/state-and-ownership.md) |
| Understand competition records and handoffs | [Competition model](architecture/competition-model.md) |
| Show readiness to users | [Readiness vocabulary](architecture/readiness-vocabulary.md) |
| Read an architecture decision | [Decision records](architecture/decisions/README.md) |
| See how other sports and federations could be supported later | [Multi-sport direction](architecture/multi-sport-direction.md) |
| Look up an HTTP route | [Route inventory](reference/routes.md) |
| Integrate with the platform | [Integration contracts](reference/integration-contracts.md) |
| Check how long data is kept | [Data retention](reference/data-retention.md) |
| Set up a development environment and contribute | [Contributing](../CONTRIBUTING.md) |
| Write or run tests | [Testing guide](development/testing.md) |
| Translate the platform or add a language | [Translations](development/translations.md) |
| Understand the CI checks | [CI and quality gates](development/ci.md) |
| Deploy a new server | [Deployment guide](operations/deployment.md) |
| Upgrade production or roll back | [Release runbook](operations/release-runbook.md) |
| Record or read upgrade notes for a change | [Upgrade notes](operations/upgrade-notes.md) |
| Fix a known problem | [Troubleshooting](operations/troubleshooting.md) |
| Qualify a release candidate | [Release qualification](release/README.md) |
| Run acceptance tests | [Acceptance suites](release/acceptance/README.md) |
| See what is planned or still open | [Roadmap](roadmap.md) |

Module-specific behaviour, models and configuration live in each addon's
`README.md` (for example [`sports_federation_portal/README.md`](../sports_federation_portal/README.md)).
The [module catalogue](overview/modules.md) links all of them.

## Structure

```text
README.md                    Repository front door: what it is and how to install it
CONTRIBUTING.md              How to contribute: setup, tests, checks, documentation rules
MODULE_OWNERS.yaml           Machine-readable module ownership (validated by CI)
docs/
├── README.md                This map
├── roadmap.md               Current priorities, open gaps and deferred work
├── overview/                Product scope, module catalogue, glossary
├── user-guide/              How operators use the back office
├── workflows/               Authoritative business processes, one per subject
├── architecture/            Design, conventions, ownership, decisions (ADRs)
├── reference/               Routes, integration contracts, data retention
├── development/             Testing, CI and contributor tooling
├── operations/              Deployment, release runbook, upgrade notes, troubleshooting
└── release/                 Release qualification, acceptance suites, agent briefs
sports_federation_*/README.md  Module-level behaviour and configuration
```

## Where new information belongs

| Kind of change | Update |
| --- | --- |
| New or changed state, transition or business rule | The matching file in [`workflows/`](workflows/README.md) and, for core records, [state and ownership](architecture/state-and-ownership.md) |
| New model, field, wizard or service | The owning addon `README.md` |
| New or changed convention that applies to every addon | [Technical reference](architecture/technical-reference.md) |
| A decision that changes a cross-cutting boundary | A new or updated record in [`architecture/decisions/`](architecture/decisions/README.md) |
| New, changed or removed HTTP route | [Route inventory](reference/routes.md), `ci/contracts/route_inventory.json` and, when partner-facing, [integration contracts](reference/integration-contracts.md) |
| New or changed menu | [Backend navigation](user-guide/backend-navigation.md) and, for competition work, [competition workflow](user-guide/competition-workflow.md) |
| Schema change, migration or upgrade-sensitive behaviour | A new entry at the top of [upgrade notes](operations/upgrade-notes.md) |
| New procedure for operators running production | [Release runbook](operations/release-runbook.md) or [troubleshooting](operations/troubleshooting.md) |
| New acceptance scenario | The matching suite in [`release/acceptance/`](release/acceptance/README.md) |
| New retention window or cleanup job | [Data retention](reference/data-retention.md) |
| New addon or ownership change | `MODULE_OWNERS.yaml` and the [module catalogue](overview/modules.md) |

## Writing rules

- **One subject, one file.** Link to the authoritative file instead of copying
  its content. If two files disagree, fix the one that is not authoritative.
- **Describe the current system.** Do not write delivery reports, patch notes,
  "implemented in this change" sections or validation logs into the
  documentation. Git history and pull requests keep that record. Upgrade
  evidence belongs only in [upgrade notes](operations/upgrade-notes.md).
- **No delivery labels.** Use names that describe the purpose ("Release
  candidate qualification"), not delivery order or numbering such as numbered
  phases, "P0" or "Priority A". `ci/check_delivery_language.py` enforces part of
  this rule.
- **No dated section titles.** A heading such as "Navigation baseline
  (2026-05-25)" becomes stale the day it is written. Put dates only in the
  metadata block or in upgrade notes.
- **Use operator language for operators.** User guides and workflows use menu
  labels and business terms from the [glossary](overview/glossary.md); model
  names belong in technical sections.
- **Use repository-relative paths.** Paths start at the repository root
  (`docs/…`, `ci/…`, `sports_federation_portal/…`) without an `odoo/` or
  `addons/` prefix. Use relative Markdown links between documents.
- **File names** are lower-case with hyphens. Only `README.md` and the root
  `CONTRIBUTING.md` use upper case.

## Metadata and freshness

Documents listed in `ci/contracts/documentation_freshness.json` start with a
metadata block:

```text
Owner: <team>
Last reviewed: YYYY-MM-DD
Review cadence: Every release
```

`ci/check_doc_freshness.py` fails when a tracked document misses this block or
when an `Every release` document has not been reviewed for 120 days.
`docs/roadmap.md` and `docs/operations/release-runbook.md` also carry
`Release train: YYYY.MM`, which `ci/check_release_train.py` keeps aligned.

## Checks that read the documentation

Several CI checks read documents by path. Moving or renaming one of these files
requires updating the check in the same change.

| Document | Checked by |
| --- | --- |
| `user-guide/backend-navigation.md`, `user-guide/competition-workflow.md` | `ci/check_competition_ui_workflow.py`, `ci/check_competition_workflow_simplification.py` |
| `architecture/competition-model.md` | `ci/check_competition_workflow_simplification.py` |
| `workflows/tournament-lifecycle.md`, `workflows/result-pipeline.md`, `workflows/standings-lifecycle.md` | `ci/check_workflow_state_contracts.py` via `ci/contracts/workflow_state_contracts.json` |
| `reference/routes.md`, `reference/integration-contracts.md` | `ci/check_public_route_cutover_docs.py`, `ci/check_release_qualification.py`, `ci/check_migration_review.py` |
| `operations/release-runbook.md`, `roadmap.md` | `ci/check_migration_rehearsal_contract.py`, `ci/check_release_train.py` |
| `operations/upgrade-notes.md`, `architecture/technical-reference.md`, `architecture/state-and-ownership.md` | `ci/check_migration_review.py` |
| `release/pilot-scenario.md` | `ci/check_rc_product_readiness.py`, `ci/check_release_focus_contract.py` |
| `release/acceptance/competition-acceptance.md`, `release/stabilization-plan.md` | `ci/check_release_qualification.py` |
| Every Markdown file | `ci/check_markdown_links.py`, `ci/check_delivery_language.py`, `ci/check_legacy_engine_removed.py` (under `docs/`) |

Run the documentation checks before pushing:

```bash
python3 ci/check_doc_freshness.py
python3 ci/check_markdown_links.py
python3 ci/check_delivery_language.py
python3 ci/check_release_train.py
python3 ci/check_competition_ui_workflow.py
python3 ci/check_workflow_state_contracts.py
```

## Local CI automation

- [Local full CI and bounded repair](operations/local-ci-repair.md)
