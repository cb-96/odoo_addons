# Release Evidence

Release evidence is generated outside the repository and is bound to one commit. It is not source code and must not be committed.

## Generate evidence

```bash
scripts/ci/run_release_baseline.sh
```

The default output is `${TMPDIR:-/tmp}/sports-federation-release-baseline/<commit>/`. Override it with `RELEASE_BASELINE_EVIDENCE_DIR`, but keep it outside the repository.

## Validate existing evidence

```bash
python3 ci/check_release_evidence.py \
  --evidence-dir /path/to/evidence \
  --commit "$(git rev-parse HEAD)" \
  --require-passing
```

The validator rejects missing lanes, invalid records, modified logs, stale summaries, and evidence captured for another commit.

## Known failures

`ci/contracts/known_release_failures.json` is an accountability registry, not a release waiver. Every entry requires an owner, GitHub issue, exact test, reason, and expiry date. Expired entries fail static validation. A known failure still keeps the corresponding release lane red.

## Release decision

A releasable summary has `status: passed`, `complete: true`, and no failed, skipped, mismatched, or invalid lanes.
