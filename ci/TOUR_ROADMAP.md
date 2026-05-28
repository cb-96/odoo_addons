# CI Tour Roadmap

> **Purpose**: Track all planned and completed Python integration "tour" tests.
> A tour is a single deterministic `TransactionCase` test method (or class) that
> walks a complete real-world workflow from start to finish, verifying every
> state transition and key invariant along the way.
>
> **Convention**:
> - One file per workflow domain, named `test_tour_<domain>.py`
> - Lives in the `tests/` folder of the most relevant module
> - Registered in that module's `tests/__init__.py`
> - Assigned to a CI suite in `ci/run_tests.sh`

---

## Status Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Implemented and passing |
| 🔄 | In progress |
| 📋 | Planned — spec complete |
| 💡 | Proposed — needs scoping |

---

## Implemented Tours

### ✅ T-01: Full Tournament Lifecycle (RR → Knockout)

- **File**: `sports_federation_competition_engine/tests/test_tournament_tour.py`
- **Class**: `TestTournamentTour`
- **Suite**: `competition_core`
- **Workflow**: `WORKFLOW_TOURNAMENT_LIFECYCLE.md`
- **Tests**:
  - `test_full_tournament_tour_9_teams` — 9-team RR → KO with standings, progression, champion
  - `test_participant_withdrawal_reduces_schedule_scope` — withdraw before schedule, confirm exclusion
  - `test_knockout_only_tournament` — 8-team straight KO bracket, no group stage

---

### ✅ T-02: Result Pipeline — Submit / Verify / Approve / Contest / Correct

- **File**: `sports_federation_result_control/tests/test_tour_result_pipeline.py`
- **Class**: `TestTourResultPipeline`
- **Suite**: `competition_core`
- **Workflow**: `WORKFLOW_RESULT_PIPELINE.md`
- **Tests**:
  - `test_result_pipeline_full_cycle` — draft → submitted → verified → approved → contested → corrected

---

### ✅ T-03: Match Day Operations — Roster + Sheet + Referees + Result

- **File**: `sports_federation_officiating/tests/test_tour_match_day.py`
- **Class**: `TestTourMatchDay`
- **Suite**: `people_rosters_rules`
- **Workflow**: `WORKFLOW_MATCH_DAY_OPERATIONS.md`
- **Tests**:
  - `test_match_day_referee_assignment_lifecycle` — referee assign → confirm → sheet → approve → done

---

### ✅ T-04: Roster Management — Activation, Eligibility Blocks, Mid-Season Change

- **File**: `sports_federation_rosters/tests/test_tour_roster_lifecycle.py`
- **Class**: `TestTourRosterLifecycle`
- **Suite**: `people_rosters_rules`
- **Workflow**: `WORKFLOW_ROSTER_MANAGEMENT.md`
- **Tests**:
  - `test_roster_lifecycle_and_match_sheet_workflow` — draft → active → mid-season swap → closed

---

### ✅ T-05: Season Registration — Club Self-Service to Confirmation

- **File**: `sports_federation_base/tests/test_tour_season_registration.py`
- **Class**: `TestTourSeasonRegistration`
- **Suite**: `competition_core`
- **Workflow**: `WORKFLOW_SEASON_REGISTRATION.md`
- **Tests**:
  - `test_season_registration_full_lifecycle` — season open → register → confirm → enrol team → close

---

### ✅ T-06: Officiating — Assignment Lifecycle and Shortage Detection

- **File**: `sports_federation_officiating/tests/test_tour_officiating.py`
- **Class**: `TestTourOfficiating`
- **Suite**: `people_rosters_rules`
- **Workflow**: `WORKFLOW_OFFICIATING.md`
- **Tests**:
  - `test_officiating_full_lifecycle` — assign referees → confirm → match done → assignments done

---

### ✅ T-07: Discipline — Incident to Case to Sanction to Suspension

- **File**: `sports_federation_discipline/tests/test_tour_discipline_pipeline.py`
- **Class**: `TestTourDisciplinePipeline`
- **Suite**: `people_rosters_rules`
- **Workflow**: `WORKFLOW_DISCIPLINE_PIPELINE.md`
- **Tests**:
  - `test_discipline_pipeline_full_cycle` — incident → case → sanction → suspension → ineligibility

---

### ✅ T-08: Finance Events — Lifecycle and Auto-Creation Triggers

- **File**: `sports_federation_finance_bridge/tests/test_tour_finance_lifecycle.py`
- **Class**: `TestTourFinanceLifecycle`
- **Suite**: `finance_reporting`
- **Workflow**: `WORKFLOW_FINANCIAL_TRACKING.md`
- **Tests**:
  - `test_finance_event_full_lifecycle` — draft → confirmed → settled; cancel path; idempotent create_from_source

---

### ✅ T-09: Public Site — Tournament Publication and Editorial Scheduling

- **File**: `sports_federation_public_site/tests/test_tour_publication.py`
- **Class**: `TestTourPublication`
- **Suite**: `release_surfaces`
- **Workflow**: `WORKFLOW_PUBLIC_PUBLICATION.md`
- **Tests**:
  - `test_publication_lifecycle` — draft → scheduled → published → archived; can_access_publicly() gate

---

### ✅ T-10: Compliance — Document Submission, Approval, and Compliance Check

- **File**: `sports_federation_compliance/tests/test_tour_compliance.py`
- **Class**: `TestTourCompliance`
- **Suite**: `people_rosters_rules`
- **Workflow**: `WORKFLOW_COMPLIANCE_MANAGEMENT.md`
- **Tests**:
  - `test_compliance_full_lifecycle` — submit → approve → compliant; reject → non_compliant; re-approve

---

### ✅ T-11: Governance Override — Late Registration Exception

- **File**: `sports_federation_governance/tests/test_tour_governance_override.py`
- **Class**: `TestTourGovernanceOverride`
- **Suite**: `ops_and_notifications`
- **Workflow**: `WORKFLOW_GOVERNANCE_OVERRIDE.md`
- **Tests**:
  - `test_governance_override_approval_path` — submit → approve → implement → close
  - `test_governance_override_rejection_path` — submit → reject → close

---

### ✅ T-12: Data Import — Participant Bulk Import with Dry-Run Validation

- **File**: `sports_federation_import_tools/tests/test_tour_data_import.py`
- **Class**: `TestTourDataImport`
- **Suite**: `competition_core`
- **Workflow**: `WORKFLOW_DATA_IMPORT.md`
- **Tests**:
  - `test_import_clubs_dry_run_then_live` — dry-run validates, live commit creates records idempotently
  - `test_import_approval_invalidated_by_file_change` — file change after approval resets approval state

---

---

### ✅ T-13: Standings Computation — Full Lifecycle

- **File**: `sports_federation_standings/tests/test_tour_standings.py`
- **Class**: `TestTourStandings`
- **Suite**: `competition_core`
- **Tests**:
  - `test_standing_starts_draft` — new standing has no lines and is draft
  - `test_recompute_with_no_matches` — recompute with no matches creates zero-stat lines
  - `test_recompute_correct_points` — points computed per rule set (W=3, D=1, L=0)
  - `test_lines_sorted_by_points_then_wins` — ranking order: pts → wins → GD → GF → name
  - `test_tiebreak_notes_populated_for_tied_teams` — tiebreak_notes set when teams share same pts
  - `test_freeze_blocks_recompute` — frozen standing raises ValidationError without force flag
  - `test_force_recompute_works_on_frozen` — force_recompute context overrides the freeze block
  - `test_unfreeze_allows_recompute` — action_unfreeze transitions frozen → computed
  - `test_contested_match_excluded_when_flag_present` — include_in_official_standings=False excluded (skips if result_control not installed)

---

### ✅ T-13b: Club Referee Duty — Full Nomination Lifecycle

- **File**: `sports_federation_officiating/tests/test_tour_club_referee_duty.py`
- **Class**: `TestTourClubRefereeDuty`
- **Suite**: `people_rosters_rules`
- **Tests**:
  - `test_full_happy_path` — draft → open → nominated → confirmed; assignment created
  - `test_rejection_and_renomination_cycle` — nominated → rejected → re-nominated → confirmed
  - `test_cross_club_nomination_blocked` — player from wrong club raises ValidationError
  - `test_cancel_resets_to_draft` — action_cancel clears nominee and resets to draft
  - `test_cancel_blocked_on_confirmed` — action_cancel raises on confirmed duty
  - `test_nomination_deadline_72h_before_match` — nomination_deadline = match_date − 72h
  - `test_deadline_overdue_flag_past_match` — is_deadline_overdue True for open past-deadline duty
  - `test_deadline_overdue_false_when_confirmed` — confirmed duty never overdue
  - `test_duplicate_duty_blocked` — unique constraint rejects second (match, club, role)
  - `test_pending_count_on_match` — club_duty_pending_count increments on open, decrements on confirm
  - `test_display_name_is_readable` — display_name includes club name

---

### ✅ T-15: Portal Workflows — Club Representative End-to-End

- **File**: `sports_federation_portal/tests/test_tour_portal_workflows.py`
- **Class**: `TestTourPortalWorkflows`
- **Suite**: `portal_public_ops`
- **Tests**:
  - `test_portal_club_scope_ids_returns_own_club` — portal_club_scope_ids only yields rep's club
  - `test_portal_user_can_submit_season_registration` — creates + submits registration for own team
  - `test_portal_user_cannot_register_rival_team` — AccessError/ValidationError on other club's team
  - `test_portal_user_can_create_roster` — roster created for own team
  - `test_portal_user_cannot_see_rival_roster` — record rule hides rival rosters
  - `test_portal_user_can_nominate_player_for_open_duty` — nominates own-club player
  - `test_portal_user_cannot_nominate_player_from_wrong_club` — ValidationError on wrong-club player
  - `test_rival_user_cannot_see_own_clubs_duty` — isolation: rival can't read our duty
  - `test_portal_user_can_submit_match_result` — result submitted → pending_approval
  - `test_rival_user_cannot_access_our_pending_result` — record rule isolation on results
  - `test_portal_layout_values_include_pending_duty_count` — federation_pending_duties_count ≥ 1
  - `test_portal_layout_values_duties_zero_for_rival_user` — rival user sees no our-club duties

---

## Per-Suite Assignment

| CI Suite | Tours |
|----------|-------|
| `competition_core` | T-01, T-02, T-05, T-12, T-13 |
| `people_rosters_rules` | T-03, T-04, T-06, T-07, T-10, T-13b |
| `finance_reporting` | T-08 |
| `release_surfaces` | T-09 |
| `ops_and_notifications` | T-11 |
| `portal_public_ops` | T-15 |

- **Suite**: `people_rosters_rules`
