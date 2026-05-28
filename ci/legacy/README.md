# CI Legacy Assets

This folder contains deprecated CI compose variants kept for historical reproducibility.

Active path:
- Use ci/docker-compose.ci.yaml with ci/run_tests.sh for all maintained CI runs.

Legacy compose files:
- Stored under ci/legacy/compose/
- Not used by the main CI workflow
- Do not add new compose variants in ci/ root

If you need a temporary experiment, place it under ci/legacy/compose/ and document why in the PR.
