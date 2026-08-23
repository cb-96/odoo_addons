# Documentation map

Keep current guidance close to the repository entry points. Avoid creating a
new document when the information belongs in one of the maintained references
below.

## Start here

- [Repository overview](../README.md)
- [Contributing and CI](../CONTRIBUTING.md)
- [Context and ownership](../CONTEXT.md)
- [Technical architecture](../TECHNICAL_NOTE.md)
- [Testing guide](../TESTING_GUIDE.md)
- [Deployment guide](../DEPLOYMENT_GUIDE.md)
- [Release runbook](../RELEASE_RUNBOOK.md)
- [Troubleshooting](../TROUBLESHOOTING.md)

## Stable references

- [Integration contracts and notification configuration](../INTEGRATION_CONTRACTS.md)
- [Data retention policy](../DATA_RETENTION_POLICY.md)
- [State and ownership matrix](../STATE_AND_OWNERSHIP_MATRIX.md)
- [Route inventory](../ROUTE_INVENTORY.md)
- [Module ownership](../MODULE_OWNERS.yaml)
- [Architecture decisions](../adr/README.md)
- [OpenAPI contracts](../openapi/integration_v1.yaml)

## Workflows

The authoritative business workflows remain in [_workflows/](../_workflows/).
Update the matching workflow whenever a state transition, ownership rule, or
operator journey changes. The workflow contract map is in
[_workflows/contracts/](../_workflows/contracts/).

Module-specific implementation notes remain beside each addon in its
`README.md`.

## Retained history

`git` history preserves superseded reviews and planning documents. Current
roadmap commitments live in [ROADMAP.md](../ROADMAP.md); do not create a second
roadmap or a standalone review snapshot for routine changes.

## Engineering contracts

- [Phase 0 source-truth contract](phase0_source_truth.md)
