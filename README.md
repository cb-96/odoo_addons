# Sports Federation — Odoo 19 addons

Odoo 19 addons that run a sports federation: clubs, teams, seasons, players
and licences, competitions from registration to final standings, game-day
operations, officiating, rosters, results, a club portal, a public website,
and the reporting, finance and governance work around them.

The repository contains one addon per domain, named
`sports_federation_<domain>`. `sports_federation_app` installs the complete
production platform.

## Install

```bash
odoo -d DATABASE -i sports_federation_app --stop-after-init
```

Add `sports_federation_demo` for development or demonstrations only. The
[deployment guide](docs/operations/deployment.md) covers a first installation
on a server; the [release runbook](docs/operations/release-runbook.md) covers
upgrades and rollback.

## Develop

```bash
cp ci/.env.example ci/.env
python -m pip install -r requirements.txt
bash ./ci/run_tests.sh --module sports_federation_standings
bash ./ci/run_tests.sh --suite competition_core
```

Odoo runs in the `odoo:19` Docker image declared in
`ci/docker-compose.ci.yaml`; no host `odoo-bin` is needed. See
[CONTRIBUTING.md](CONTRIBUTING.md) for setup, tests, checks and the change
checklist.

## Documentation

Start at the [documentation map](docs/README.md). The most used entry points:

| Topic | Document |
| --- | --- |
| What the product does | [Product overview](docs/overview/product.md) |
| Which addon owns what | [Module catalogue](docs/overview/modules.md) |
| Running a competition in the back office | [Competition workflow](docs/user-guide/competition-workflow.md) |
| Business processes | [Workflows](docs/workflows/README.md) |
| Architecture and conventions | [Architecture overview](docs/architecture/overview.md), [technical reference](docs/architecture/technical-reference.md) |
| Routes and integrations | [Route inventory](docs/reference/routes.md), [integration contracts](docs/reference/integration-contracts.md) |
| Testing and CI | [Testing guide](docs/development/testing.md), [CI and quality gates](docs/development/ci.md) |
| Releasing | [Release qualification](docs/release/README.md), [upgrade notes](docs/operations/upgrade-notes.md) |
| Current priorities and open gaps | [Roadmap](docs/roadmap.md) |

Each addon has its own `README.md` with its models, behaviour and
configuration.

## Review bundles

`python3 source_collector.py` regenerates the current source, JSONL and Git
metadata bundles used for code review. Only the newest run directory per
category under `artifacts/` is collected. The bundles are review artifacts and
are not committed.
