# Intuitiveness Review Checklist

Use this checklist for major UX, workflow, naming, and navigation changes.

## Scope Trigger

- Applies to changes that add or rename core user-facing nouns.
- Applies to changes that introduce or change a primary entry point.
- Applies to portal/public/backend surfaces that expose workflow states.

## Required Review Questions

- Primary noun set: Is one stable noun used across backend, portal, public, and docs?
- Primary entry point: Is there one obvious start for the highest-frequency task?
- Next-step guidance: Does each blocking/empty state explain what to do next?
- State labels: Are displayed states human-facing labels instead of raw model values?
- Cross-module handoff: Does the screen link directly to the next owning action when work crosses modules?

## Delivery Requirements

- Update module README and relevant workflow docs when terminology or entry points change.
- Add or update focused tests for state-label rendering and flow entry expectations.
- Avoid adding parallel "primary" routes for the same frequent task.
- Keep advanced/recovery routes available but visually secondary.

## Fast Signoff

- [ ] Nouns are stable.
- [ ] One primary start exists.
- [ ] Blocking states explain next actions.
- [ ] Human-facing state labels are used.
- [ ] Handoffs are explicit.
- [ ] Docs and tests were updated.