# Release Train Convention

Last updated: 2026-04-18
Owner: Federation Platform Team
Last reviewed: 2026-04-18
Review cadence: Every release
Release train: 2026.04

This document defines the repository-wide release cadence so roadmap updates,
upgrade notes, and operator runbooks refer to the same operating window.

## Train ID Format

- Use `YYYY.MM` for the active train identifier.
- Cut a new train when the federation operating window changes materially.
- Archive the previous roadmap when the active train changes.

## Shared Release Surfaces

The following surfaces must carry the active `Release train:` metadata:

- `ROADMAP.md`
- `RELEASE_RUNBOOK.md`
- this file

Upgrade-sensitive changes should also reference the active train in at least one
release-note surface, typically the module README or the migration script that
lands with the change.

## Versioning Convention

- Odoo module manifests keep the standard `19.0.x.y.z` module version format.
- The release train does not replace manifest versions; it provides the shared
  cadence that ties roadmap work, migrations, and runbook checkpoints together.
- Breaking public integration changes still follow the contract versioning and
  deprecation policy documented in `INTEGRATION_CONTRACTS.md`.

## Release Window Rules

Before cutting a release branch for a new train:

1. Archive the superseded roadmap snapshot.
2. Update `Release train:` in `ROADMAP.md`, `RELEASE_RUNBOOK.md`, and this file.
3. Confirm migration review surfaces and module release notes reflect the same
   train for upgrade-sensitive changes.
4. Run the documentation and migration guardrails before promoting the train.