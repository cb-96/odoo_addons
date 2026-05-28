# Documentation Lifecycle

This repository uses a three-lane documentation model to reduce sprawl and keep docs actionable.

## Active

Purpose:
- Operational and current references used in day-to-day development and releases.

Examples:
- README.md
- CONTRIBUTING.md
- DEVELOPER_GUIDE.md
- TESTING_GUIDE.md
- TECHNICAL_NOTE.md
- CONTEXT.md
- RELEASE_RUNBOOK.md
- RELEASE_TRAIN.md

Rules:
- Update in the same change set as behavior changes.
- Keep language task-oriented and current.

## Reference

Purpose:
- Stable supporting references and inventories.

Examples:
- MODULE_OWNERS.yaml
- INTEGRATION_CONTRACTS.md
- ROUTE_INVENTORY.md
- COMPATIBILITY_INVENTORY.md
- STATE_AND_OWNERSHIP_MATRIX.md
- adr/
- _workflows/

Rules:
- Version-sensitive updates should include dates and rationale.

## Archive

Purpose:
- Historical snapshots retained for auditability.

Examples:
- archive/roadmaps/ROADMAP_archive_*.md
- ci/legacy/

Rules:
- Do not use archived files as the source of truth for current behavior.
- Maintain index files for discoverability:
  - ROADMAP_ARCHIVE_INDEX.md
  - ci/legacy/README.md
