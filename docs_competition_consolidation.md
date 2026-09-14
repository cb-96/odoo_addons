# Competition architecture consolidation

The season competition is the only ordinary operator entry point.

## Canonical operator setup state

- Define divisions
- Add teams
- Define game days
- Generate schedule
- Publish schedule
- Setup complete

Technical lifecycle states remain authoritative in their owning models. They are not a second operator journey.

## Compatibility

The former `action_open_next_workspace` method remains available and delegates to `action_continue_setup`. Existing bookmarks, inherited buttons, server actions, and integrations therefore continue working.

Advanced technical workspaces remain available through `action_open_advanced_workspace` for federation managers and exceptional recovery work.

## Source consolidation boundary

The setup flow is the integration owner until the competition modules can be physically consolidated with a migration rehearsal. Model names, table names, XML IDs, security groups, publications, and audit history must remain stable throughout that move.
