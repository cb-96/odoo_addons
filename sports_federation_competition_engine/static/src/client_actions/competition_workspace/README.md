# Competition Workspace Static Architecture

This folder contains the client action that powers the competition workspace UI.

## Files

- competition_workspace.js: OWL component tree, local UI state, RPC orchestration, planner interaction logic.
- methods/*.js: extracted form, planner data/action, and publishing methods imported by the root action module. These files must remain in `web.assets_backend` alongside `competition_workspace.js` so the action module can be evaluated.
- competition_workspace.xml: templates for all workspace panels and dialogs.
- competition_workspace.scss: visual structure and interaction styling for cards, grid, and dialogs.

## Component Map

- CompetitionWorkspaceAction (root)
  - CompetitionOverviewCard
  - ProgressStepper
  - ValidationPanel
  - CollaborationPanel
  - RevisionSummaryPanel
  - GenerationPreview
  - UnscheduledMatchList
    - DraggableMatchCard
  - ScheduleGrid
    - DraggableMatchCard
  - SlotSuggestionPanel
  - FairnessSummaryPanel
  - PublishScheduleDialog
  - MobileAssignmentDialog
  - ActionConfirmDialog

## State Shape (high-level)

The root component owns all page state in one useState object.

Key groups:

- selection/navigation: activeSection, currentCompetitionId, currentDivisionId, currentGamedayId.
- planner UI: filters, selectedMatchIds, plannerLoading, plannerUnscheduledLimit.
- dialogs: mobileAssign, confirmDialog, pendingValidation.
- forms: shellForm, divisionForm, teamEntryForm, gamedayForm.
- server payload: payload, validationSnapshot, collaboration.

## Data Flow

1. onWillStart calls loadInitialData.
2. loadWorkspace fetches server payload and normalizes local selections.
3. Planner section optionally calls loadPlanner with scoped RPC filters.
4. UI interactions (assign, unassign, validate, publish) call service methods, then refresh payload/planner snapshots.

## Maintainability Conventions

- Keep section metadata centralized in competition_workspace.js constants:
  - WORKSPACE_SECTIONS
  - DIVISION_PLANNING_FORMAT_OPTIONS
  - DIVISION_CATEGORY_OPTIONS
  - DIVISION_GENDER_OPTIONS
- In XML, prefer t-foreach loops against these constants over duplicating option/button blocks.
- Root template decomposition:
  - CompetitionWorkspaceSectionOverview
  - CompetitionWorkspaceSectionTeams
  - CompetitionWorkspaceSectionRounds
  - CompetitionWorkspaceSectionGamedays
  - CompetitionWorkspaceSectionNav
  - CompetitionWorkspaceSectionPlanner
  - CompetitionWorkspaceSectionPublish
  Keep the root action template focused on flow control and section dispatch.
- Keep view-only formatters as pure helpers near file top (for example: isPlannerBusyState).
- Avoid adding business rules directly in templates; put logic into getters on CompetitionWorkspaceAction.
- Keep planner-heavy methods grouped in the dedicated JS regions:
  - Planner: read model and UI state helpers
  - Planner: selection, filtering, and suggestions
  - Planner: assignment and operation actions

## Common Safe Refactor Targets

- Move repeated template chunks into dedicated child components.
- Group planner-only methods together to reduce context switching in the root class.
- Convert repeated badge tone logic into one reusable helper (already partially done via stateTone + badgeClass).

## Where To Start When Debugging

- Rendering/state issue in a section: inspect corresponding getter in competition_workspace.js and matching template block in competition_workspace.xml.
- Assignment/drag issues: DraggableMatchCard + ScheduleGrid + root handlers (onDragStartMatch, assign/unassign methods).
- Publish/validation issues: activeValidation, requestConfirmValidation, confirmValidation, and PublishScheduleDialog props.
