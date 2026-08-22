---
name: module-change-scaffold
description: 'Scaffolds complete Odoo module changes in this repo. Use when adding or changing a model, wizard, service, controller, view, ACL, or data file so the owning addon gets all required wiring, tests, and docs in one pass.'
argument-hint: 'Describe the feature or change and the target addon if known'
user-invocable: true
---

# Module Change Scaffold

## What This Skill Produces

This skill turns a requested feature or module change into a complete repo-conformant change set: code, manifest wiring, security, views, tests, and docs.

Use it when:
- adding a new persistent model
- extending an existing model with fields, constraints, or actions
- adding a wizard or service flow
- adding portal behavior or templates
- changing workflows that must stay aligned with repo docs

## Repo Principles

- Keep changes in the owning addon whenever possible.
- Prefer service logic in `services/` and keep models thinner when behavior is algorithmic.
- Use `wizards/` for admin-driven generation and confirmation flows.
- Add focused tests for every behavior change.
- Update docs in the same change set.

## Procedure

1. Pick the owning addon.
   - Do not spread behavior across multiple addons unless the architecture already does so.
   - If the request crosses boundaries, identify the primary owner and the inherited extension points.

2. Classify the change.
   - **Model change**
   - **New model**
   - **Wizard flow**
   - **Service / scheduling logic**
   - **Portal / controller / template**
   - **Security / ACL / ownership**

3. Apply the right scaffold.

### For model changes

Touch as needed:
- `models/*.py`
- `models/__init__.py`
- `views/*.xml`
- `security/ir.model.access.csv` when new models are introduced
- `tests/`

### For new persistent models

Add:
- model class
- package export
- ACL row
- form/list/search view if user-facing
- manifest `data` registration
- at least one creation or workflow test

### For wizards

Add:
- transient model in `wizards/`
- `wizards/__init__.py` export
- wizard view XML
- manifest `data` entry
- summary, validation, and confirmation tests

### For services

Add or change:
- `services/*.py`
- the smallest public caller from model or wizard layer
- deterministic regression tests around the service entrypoint

### For portal flows

Add or change:
- `controllers/*.py`
- templates under `views/`
- ownership and access tests using portal users and club representatives
- `with_user(...)` assertions for positive and negative paths

4. Wire the manifest correctly.
   - Update `depends` when inherited models or XML IDs come from another addon.
   - Register new XML and CSV files in `data`.

5. Add the smallest meaningful tests.
   - Prefer `TransactionCase` unless route rendering itself is the behavior under test.
   - Cover one happy path and one guard or failure path.

6. Sync docs.
   - Update the affected addon `README.md`.
   - Update the relevant `_workflows/*.md` file when behavior changes.
   - Update top-level docs like `TECHNICAL_NOTE.md`, `CONTEXT.md`, or ownership matrices when the change is cross-cutting.

7. Run the smallest useful CI scope first.
   - Start with the owning module.
   - Broaden if the change touched shared services, inherited extensions, portal/public behavior, or CI wiring.

## Decision Points

### If the request is mostly algorithmic

Prefer a service change plus regression tests, not a heavy model method.

### If the request is interactive and admin-driven

Prefer a wizard with preview and confirm behavior.

### If the request affects club or portal ownership

Add access tests and record-rule coverage, not just controller code.

### If the request changes states, deadlines, or advancement rules

Update both tests and the relevant workflow docs.

## Completion Checklist

Before finishing, verify:
- code is in the right addon
- package exports are updated
- manifest `depends` and `data` are correct
- security entries exist for new models
- tests cover the main behavior
- docs were updated where behavior changed
- focused CI passed

## Useful Repo Anchors

- `CONTRIBUTING.md`
- `.github/copilot-instructions.md`
- `TECHNICAL_NOTE.md`
- `CONTEXT.md`

## Example Invocations

- `/module-change-scaffold add a new tournament registration helper in sports_federation_portal with ACLs, tests, and docs`
- `/module-change-scaffold extend sports_federation_venues with a new scheduling field and the required view, test, and README updates`
- `/module-change-scaffold create a wizard spanning sports_federation_format and sports_federation_scheduling and wire the manifests, tests, and workflow docs`
