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

- [Foundation source-truth contract](workflow_source_truth.md)

- [Delivery roadmap](DELIVERY_ROADMAP.md): executable post-stabilization milestones and exit criteria.

- [Competition UI workflow](COMPETITION_UI_WORKFLOW.md)
- [Release candidate roadmap](RELEASE_CANDIDATE_ROADMAP.md)
- [Competition engine roadmap](COMPETITION_ENGINE_ROADMAP.md)
- [Competition operations QoL roadmap](COMPETITION_OPERATIONS_QOL_ROADMAP.md)
- [Release pilot scenario](RELEASE_PILOT_SCENARIO.md)

- [Public competition API](PUBLIC_COMPETITION_API.md)
