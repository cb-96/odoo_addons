"""Run scheduled jobs in bounded, isolated batches.

A scheduled job that handles every record in one transaction has two problems:
one bad record rolls back the whole run (so nothing is ever processed until
someone fixes it), and a large backlog holds locks and memory for as long as
the run takes.

These helpers:

- run each record in its own savepoint, so a failing record is logged and
  skipped while the others are saved;
- process records in batches and, when running as a scheduled job, commit
  after each batch, so finished work survives a later crash or timeout;
- re-raise database concurrency errors (serialization failure, deadlock), so
  the job is retried as a whole instead of half-applied.

Intermediate commits only happen when the job runs as a scheduled job
(``cron_id`` in the context, set by Odoo's cron runner) and never in tests.
Called from anywhere else (tests, a button, a shell) the helpers still isolate
records and bound each step, but leave the transaction to the caller.
"""

import logging

from psycopg2.errors import DeadlockDetected, SerializationFailure

_logger = logging.getLogger(__name__)

RETRYABLE_ERRORS = (DeadlockDetected, SerializationFailure)
DEFAULT_BATCH_SIZE = 200


def commits_between_batches(env):
    """Whether a batch may be committed before the job ends."""
    return bool(env.context.get("cron_id")) and not env.registry.in_test_mode()


def commit_batch(env):
    if commits_between_batches(env):
        env.cr.commit()
        # Committed records stay in the cache, but nothing else may assume
        # what another transaction did meanwhile.
        env.invalidate_all()


def process_each(records, process, *, label, batch_size=DEFAULT_BATCH_SIZE):
    """Call ``process(record)`` for every record, each in its own savepoint.

    Returns ``(done, failed)`` counts. A failing record is logged with its id
    and skipped; concurrency errors are re-raised.
    """
    env = records.env
    ids = list(records.ids)
    done = failed = 0
    for start in range(0, len(ids), batch_size):
        for record in records.browse(ids[start : start + batch_size]):
            try:
                with env.cr.savepoint():
                    process(record)
            except RETRYABLE_ERRORS:
                raise
            except Exception:  # pylint: disable=broad-except
                failed += 1
                _logger.exception(
                    "%s failed for %s(%s); the other records continue.",
                    label,
                    record._name,
                    record.id,
                )
                continue
            done += 1
        commit_batch(env)
    if failed:
        _logger.error("%s: %s record(s) failed, %s done.", label, failed, done)
    return done, failed


def for_each_chunk(records, handle, *, batch_size=DEFAULT_BATCH_SIZE):
    """Call ``handle(chunk)`` per batch of ``records``; commit between batches.

    For set-based work such as retention purges: a chunk fails as a whole and
    the error propagates (the caller records it), but chunks already handled
    stay handled when running as a scheduled job. Returns the sum of what
    ``handle`` returns (counts), treating ``None`` as 0.
    """
    env = records.env
    ids = list(records.ids)
    total = 0
    for start in range(0, len(ids), batch_size):
        total += handle(records.browse(ids[start : start + batch_size])) or 0
        commit_batch(env)
    return total
