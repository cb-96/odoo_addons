# Documentation Review

Review date: 2026-09-04
Reviewed source: commit `035b5167f6e42c0fcaabe9c73c097f6c63167400`
Owner: Federation Platform Team

## Scope

The second pass reviewed all repository Markdown, all 26 addon manifests,
backend menu XML, portal routes, release scripts, CI documentation contracts,
controller routes, workflow descriptions, OpenAPI references, and addon README
coverage.

## Corrections

- Added the canonical competition UI and recovery guide.
- Corrected obsolete menu terminology across workflows and ownership docs.
- Added menu-to-documentation drift validation.
- Restored integration and public-feed OpenAPI contracts, examples, and error
  documentation required by code and CI.
- Added missing Calendar and Competition Core READMEs.
- Replaced implementation-era roadmap priority labels with durable headings.
- Corrected delivery statuses and the release documentation index.
- Added RC logfile diagnostics and corrected a deterministic SHA test fixture.

## Enforced checks

```text
ci/check_markdown_links.py
ci/check_doc_freshness.py
ci/check_delivery_language.py
ci/check_competition_ui_workflow.py
ci/check_openapi_contracts.py
```

## Evidence still required

Release baseline execution and migration rehearsal remain pending until they run
against a clean committed candidate and an approved production-like backup.
That is release evidence still to collect, not unresolved documentation debt.
