# Foundation: Repository Source Truth

Owner: Federation engineering
Last reviewed: 2026-08-23
Review cadence: Every release

Foundation establishes a trustworthy input boundary for reviews and release checks.

## Guarantees

- Addons are discovered from repository manifests instead of a maintained allowlist.
- Every internal `sports_federation_*` dependency must resolve to a collected addon.
- Manifest data files and explicit asset files must exist and be collected.
- Root documentation, ADRs, workflows, CI scripts, shell scripts and the collector itself are collected.
- Generated CI logs and generated review outputs are excluded.
- Workflow contract failures identify missing or invalid source without Python tracebacks.
- Documentation freshness is governed by `ci/contracts/documentation_freshness.json`.
- CI validates manifests, internal dependencies, initializer imports and ACL presence.

## Required verification

```bash
python source_collector.py
python ci/check_source_collector_contract.py
python ci/check_addon_integrity.py
python ci/check_workflow_state_contracts.py
python ci/check_doc_freshness.py
```

A release candidate must not proceed while any command fails.
