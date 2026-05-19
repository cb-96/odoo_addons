# ADR-0001: Portal Trust Boundaries

Last updated: 2026-04-18
Owner: Federation Platform Team
Last reviewed: 2026-04-18
Review cadence: Every release

## Status

Accepted

## Context

Portal club representatives need to create and update federation records that
their base ACLs do not own directly. The repository already separates portal
ownership checks from broad backend access, but that policy was previously
spread across controllers, model methods, and release notes.

## Decision

Portal writes will continue to use explicit model-owned privilege boundaries:

- controllers load the request user, resolve the allowed club scope, and reject
  requests that fall outside that scope before any privileged write occurs
- model helpers execute the actual create or state transition through
  `with_user(user).sudo()` so the request user remains visible in audit fields
  while ACL bypass stays narrow and intentional
- ORM-level ownership constraints mirror the controller checks so bypassing a
  browser route does not widen access
- portal and `HttpCase` regression tests remain mandatory for any new privileged
  write surface

## Consequences

- privilege escalation logic stays centralized and reviewable instead of being
  reimplemented in each controller
- request-user ownership remains visible in `create_uid` and `write_uid`
- new portal features must add or reuse model-level helpers instead of writing
  through raw controller `sudo()` flows