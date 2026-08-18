/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { CompetitionWorkspaceFormMethods } from "./methods/competition_workspace_form_methods";
import { CompetitionWorkspacePlannerActionMethods } from "./methods/competition_workspace_planner_action_methods";
import { CompetitionWorkspacePlannerDataMethods } from "./methods/competition_workspace_planner_data_methods";
import { CompetitionWorkspacePublishingMethods } from "./methods/competition_workspace_publishing_methods";

const MOBILE_QUERY = "(max-width: 991.98px)";
const UI_STATE_STORAGE_KEY = "sports_federation_competition_engine.competition_workspace.ui_state";

// Keep top-level workspace navigation and form options in one place.
const WORKSPACE_SECTIONS = Object.freeze([
    { key: "overview", label: "Overview" },
    { key: "teams", label: "Teams" },
    { key: "rounds", label: "Rounds" },
    { key: "gamedays", label: "Gamedays" },
    { key: "planner", label: "Gameday Planner" },
    { key: "publish", label: "Publish" },
]);

const DIVISION_PLANNING_FORMAT_OPTIONS = Object.freeze([
    { value: "single_round_robin", label: "Single Round Robin" },
    { value: "double_round_robin", label: "Double Round Robin" },
    { value: "knockout", label: "Knockout" },
    { value: "pool_then_bracket", label: "Pool Then Bracket" },
    { value: "manual", label: "Manual" },
]);

const DIVISION_CATEGORY_OPTIONS = Object.freeze([
    { value: "", label: "Any" },
    { value: "senior", label: "Senior" },
    { value: "youth", label: "Youth" },
    { value: "junior", label: "Junior" },
    { value: "cadet", label: "Cadet" },
    { value: "mini", label: "Mini" },
]);

const DIVISION_GENDER_OPTIONS = Object.freeze([
    { value: "", label: "Any" },
    { value: "male", label: "Male" },
    { value: "female", label: "Female" },
    { value: "mixed", label: "Mixed" },
]);

const DEFAULT_VALIDATION = Object.freeze({
    blocking: [],
    warnings: [],
    unscheduled_matches: [],
    empty_slots: [],
});

const DEFAULT_COLLABORATION = Object.freeze({
    active_count: 0,
    active_users: [],
    same_gameday_count: 0,
    same_gameday_users: [],
    warning_message: false,
});

const DEFAULT_SCHEDULE_REVISIONS = Object.freeze({
    draft_revision: false,
    live_revision: false,
    recent_revisions: [],
});

const DEFAULT_GENERATION_PREVIEW = Object.freeze({
    action_label: false,
    description: "",
    empty_message: "No generated preview is available yet.",
    format: false,
    rounds: [],
    supported: false,
});

const DEFAULT_FAIRNESS_SUMMARY = Object.freeze({
    court_balance_gap_percent: 0,
    rest_balance_gap_minutes: 0,
    score_components: [],
    team_metrics: [],
    timeslot_balance_gap_minutes: 0,
    tracked_team_count: 0,
    warnings: [],
});

export function isPlannerBusyState({ saving = false, plannerLoading = false, publishing = false } = {}) {
    return Boolean(saving || plannerLoading || publishing);
}

export function isPlannerValidationConfirmable({
    currentGamedayId = false,
    currentPlannerState = "draft",
    saving = false,
    plannerLoading = false,
    publishing = false,
} = {}) {
    return Boolean(
        currentGamedayId
        && currentPlannerState === "planned"
        && !isPlannerBusyState({ saving, plannerLoading, publishing })
    );
}

export function formatPlannerSelectionSummary({
    selectedCount = 0,
    unscheduledCount = 0,
    assignedCount = 0,
} = {}) {
    if (!selectedCount) {
        return "No matches selected.";
    }
    return `${selectedCount} selected: ${unscheduledCount} unscheduled and ${assignedCount} assigned.`;
}

export function resolveWorkspaceSections({ competition = {}, division = false } = {}) {
    const hasCompetition = Boolean(competition?.id);
    const hasDivision = Boolean(division?.id);
    const entriesLocked = Boolean(division?.entries_locked);
    const hasMatches = Boolean(division?.match_count);
    const hasGamedays = Boolean(division?.gameday_count);
    const scheduleComplete = Boolean(
        hasDivision && division.slot_count > 0 && division.unscheduled_match_count === 0
    );
    return [
        {
            key: "overview",
            label: "Set up",
            shortLabel: "Overview",
            description: hasDivision
                ? "Review divisions and competition settings."
                : "Create or select the division you want to plan.",
            disabled: !hasCompetition,
            complete: hasDivision,
        },
        {
            key: "teams",
            label: "Add teams",
            shortLabel: "Teams",
            description: entriesLocked
                ? "Team entries are confirmed and locked."
                : "Add, confirm, and lock participating teams.",
            disabled: !hasDivision,
            complete: entriesLocked,
        },
        {
            key: "rounds",
            label: "Build schedule",
            shortLabel: "Schedule",
            description: hasMatches
                ? "The match structure has been generated."
                : "Generate rounds and matches from the locked entries.",
            disabled: !entriesLocked,
            complete: hasMatches,
        },
        {
            key: "gamedays",
            label: "Create gamedays",
            shortLabel: "Gamedays",
            description: hasGamedays
                ? "Gamedays exist and can receive planning slots."
                : "Choose dates, venue, courts, and timeslot settings.",
            disabled: !hasMatches,
            complete: hasGamedays,
        },
        {
            key: "planner",
            label: "Plan matches",
            shortLabel: "Planner",
            description: scheduleComplete
                ? "Every match has a slot. Review conflicts and fairness."
                : "Assign matches to slots and resolve scheduling conflicts.",
            disabled: !hasGamedays,
            complete: scheduleComplete,
        },
        {
            key: "publish",
            label: "Validate and publish",
            shortLabel: "Publish",
            description: division?.workspace_state === "published"
                ? "The current schedule is published."
                : "Run final checks and publish the approved schedule.",
            disabled: !hasGamedays,
            complete: division?.workspace_state === "published",
        },
    ];
}

export function shouldHandlePlannerEscape({
    key,
    activeSection,
    selectedCount = 0,
    hasPendingValidation = false,
} = {}) {
    return Boolean(
        key === "Escape"
        && activeSection === "planner"
        && (selectedCount > 0 || hasPendingValidation)
    );
}

function badgeClass(tone) {
    const resolvedTone = tone || "secondary";
    if (["warning", "info"].includes(resolvedTone)) {
        return `badge rounded-pill bg-${resolvedTone} text-dark`;
    }
    return `badge rounded-pill text-bg-${resolvedTone}`;
}

function stateTone(state) {
    const toneMap = {
        draft: "secondary",
        registration_open: "info",
        registration_locked: "warning",
        schedule_generated: "info",
        planning: "primary",
        published: "success",
        in_progress: "primary",
        completed: "success",
        archived: "dark",
        cancelled: "dark",
        confirmed: "success",
        submitted: "info",
        withdrawn: "dark",
        validated: "info",
        planned: "primary",
        locked: "dark",
        available: "success",
        reserved: "info",
        assigned: "primary",
        blocked: "danger",
        break: "warning",
        applied: "info",
        live: "success",
        undone: "warning",
        superseded: "dark",
    };
    return toneMap[state] || "secondary";
}

function applyPrototypeMethods(target, sourceClass) {
    for (const name of Object.getOwnPropertyNames(sourceClass.prototype)) {
        if (name === "constructor") {
            continue;
        }
        Object.defineProperty(target, name, Object.getOwnPropertyDescriptor(sourceClass.prototype, name));
    }
}

class StatusBadge extends Component {
    static template = "sports_federation_competition_engine.CompetitionWorkspaceStatusBadge";

    get badgeClass() {
        return badgeClass(this.props.tone || stateTone(this.props.state));
    }
}

class ProgressStepper extends Component {
    static template = "sports_federation_competition_engine.CompetitionWorkspaceProgressStepper";

    selectStep(step) {
        if (!step.disabled && this.props.onSelect) {
            this.props.onSelect(step.key);
        }
    }
    stepClass(step) {
        if (step.active) {
            return "o-active";
        }
        if (step.complete) {
            return "o-complete";
        }
        return "";
    }
}

class ValidationPanel extends Component {
    static template = "sports_federation_competition_engine.CompetitionWorkspaceValidationPanel";
    static components = { StatusBadge };
}

class CollaborationPanel extends Component {
    static template = "sports_federation_competition_engine.CompetitionWorkspaceCollaborationPanel";
    static components = { StatusBadge };
}

class RevisionSummaryPanel extends Component {
    static template = "sports_federation_competition_engine.CompetitionWorkspaceRevisionSummaryPanel";
    static components = { StatusBadge };
}

class CompetitionOverviewCard extends Component {
    static template = "sports_federation_competition_engine.CompetitionOverviewCard";
    static components = { StatusBadge };
}

class GenerationPreview extends Component {
    static template = "sports_federation_competition_engine.CompetitionWorkspaceGenerationPreview";
    static components = { StatusBadge };
}

class FairnessSummaryPanel extends Component {
    static template = "sports_federation_competition_engine.CompetitionWorkspaceFairnessSummaryPanel";
    static components = { StatusBadge };
}

class SlotSuggestionPanel extends Component {
    static template = "sports_federation_competition_engine.CompetitionWorkspaceSlotSuggestionPanel";
    static components = { StatusBadge };
}

class DraggableMatchCard extends Component {
    static template = "sports_federation_competition_engine.DraggableMatchCard";
    static components = { StatusBadge };

    get cardClass() {
        return [
            this.props.assigned ? "o-assigned" : "",
            this.props.selected ? "o-selected" : "",
        ]
            .filter(Boolean)
            .join(" ");
    }

    onDragStart(ev) {
        if (!this.props.draggable) {
            return;
        }
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", String(this.props.match.id));
        this.props.onDragStart(this.props.match.id);
    }

    onAssignClick() {
        this.props.onAssign(this.props.match.id);
    }

    onUnassignClick() {
        this.props.onUnassign(this.props.match.id);
    }

    onToggleSelection(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.props.onToggleSelected(this.props.match.id);
    }
}

class UnscheduledMatchList extends Component {
    static template = "sports_federation_competition_engine.UnscheduledMatchList";
    static components = { DraggableMatchCard, StatusBadge };

    onDropToPool(ev) {
        ev.preventDefault();
        const matchId = Number(ev.dataTransfer.getData("text/plain") || 0);
        if (matchId) {
            this.props.onUnassign(matchId);
        }
    }

    onDragOver(ev) {
        ev.preventDefault();
    }

    onLoadMore() {
        this.props.onLoadMore();
    }
}

class ScheduleGrid extends Component {
    static template = "sports_federation_competition_engine.ScheduleGrid";
    static components = { DraggableMatchCard, StatusBadge };

    get gridStyle() {
        return `grid-template-columns: minmax(6rem, 7rem) repeat(${this.props.courts.length}, minmax(13rem, 1fr));`;
    }

    get highlightedSlotIds() {
        return new Set(this.props.highlightedSlotIds || []);
    }

    slotCellClass(slot) {
        return [
            slot ? `o-state-${slot.state}` : "",
            slot && this.highlightedSlotIds.has(slot.id) ? "o-highlighted" : "",
        ]
            .filter(Boolean)
            .join(" ");
    }

    onDragOverSlot(ev) {
        ev.preventDefault();
    }

    onDropSlot(ev) {
        ev.preventDefault();
        const matchId = Number(ev.dataTransfer.getData("text/plain") || 0);
        const slotId = Number(ev.currentTarget.dataset.slotId || 0);
        if (matchId && slotId) {
            this.props.onDropMatch(matchId, slotId);
        }
    }

    onAssignClick(ev) {
        this.props.onAssign(Number(ev.currentTarget.dataset.matchId));
    }

    onUnassignClick(ev) {
        this.props.onUnassign(Number(ev.currentTarget.dataset.matchId));
    }

    onAssignSelected(ev) {
        const slotId = Number(ev.currentTarget.dataset.slotId || 0);
        if (slotId) {
            this.props.onAssignSelected(slotId);
        }
    }
}

class MobileAssignmentDialog extends Component {
    static template = "sports_federation_competition_engine.MobileAssignmentDialog";
}

class PublishScheduleDialog extends Component {
    static template = "sports_federation_competition_engine.PublishScheduleDialog";
    static components = { StatusBadge, ValidationPanel };
}

class ActionConfirmDialog extends Component {
    static template = "sports_federation_competition_engine.CompetitionWorkspaceActionConfirmDialog";
}

export class CompetitionWorkspaceAction extends Component {
    static template = "sports_federation_competition_engine.CompetitionWorkspaceAction";
    static components = {
        CollaborationPanel,
        CompetitionOverviewCard,
        FairnessSummaryPanel,
        GenerationPreview,
        MobileAssignmentDialog,
        ActionConfirmDialog,
        ProgressStepper,
        PublishScheduleDialog,
        RevisionSummaryPanel,
        ScheduleGrid,
        SlotSuggestionPanel,
        StatusBadge,
        UnscheduledMatchList,
        ValidationPanel,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        const params = this.props.action?.params || {};
        const restoredState = this.readPersistedUiState(params);
        this.heartbeatTimer = null;
        this.state = useState({
            activeSection: restoredState.activeSection || "overview",
            availableClubs: [],
            availableCourts: [],
            availableTeams: [],
            collaboration: {
                planner: false,
                workspace: false,
            },
            error: null,
            filters: {
                divisionId: restoredState.filters?.divisionId || "",
                conflictsOnly: Boolean(restoredState.filters?.conflictsOnly),
                roundNumber: restoredState.filters?.roundNumber || "",
                teamId: restoredState.filters?.teamId || "",
            },
            gamedayForm: {
                courtIds: [],
                end_time: "17:00",
                match_duration_minutes: "35",
                name: "",
                round_number: "",
                round_date: "",
                selected_gameday_id: params.gameday_id ? String(params.gameday_id) : "",
                sharedDivisionConfig: {},
                sharedDivisionIds: [],
                start_time: "09:00",
                stage_id: "",
                buffer_minutes: "5",
                venue_id: "",
            },
            stageForm: {
                auto_advance: false,
                cascade_delete: false,
                delete_reason: "",
                group_count: "4",
                qualifiers_per_group: "2",
                placement_from: "3",
                placement_to: "4",
                preset: "group_knockout",
                round_count: "3",
                target_stage_id: "",
                date_end: "",
                date_start: "",
                name: "",
                rank_from: "1",
                rank_to: "2",
                sequence: "",
                source_stage_id: "",
                stage_type: "group",
            },
            loading: true,
            mobileAssign: {
                gameday_id: params.gameday_id ? String(params.gameday_id) : "",
                match_id: "",
                open: false,
                slot_id: "",
            },
            currentCompetitionId: params.competition_id || restoredState.competitionId || false,
            currentDivisionId: params.division_id || restoredState.divisionId || false,
            currentGamedayId: params.gameday_id || restoredState.gamedayId || false,
            payload: null,
            pendingValidation: null,
            confirmDialog: {
                action: false,
                confirmLabel: "Confirm",
                message: "",
                open: false,
                title: "Please confirm",
                tone: "primary",
            },
            pendingGamedayDeletionId: false,
            plannerLoading: false,
            plannerPageSize: 40,
            plannerUnscheduledLimit: 40,
            publishing: false,
            overrideReason: {
                pending: "",
                publish: "",
            },
            saving: false,
            selectedMatchIds: [],
            slotSuggestions: {
                items: [],
                loading: false,
                matchId: false,
            },
            shellForm: {
                competition_id: "",
                competition_type: "league",
                date_end: "",
                date_start: "",
                name: "",
                season_id: "",
            },
            teamSearchLoading: false,
            divisionForm: {
                category: "",
                date_end: "",
                date_start: "",
                gender: "",
                max_consecutive_matches_per_team: "1",
                minimum_rest_minutes: "30",
                name: "",
                planning_format: "single_round_robin",
                pool_count: "2",
                pool_qualifier_count: "2",
            },
            teamEntryForm: {
                club_id: "",
                search: "",
                seed: "",
                team_id: "",
            },
            validationSnapshot: null,
            isMobile: typeof window !== "undefined" && window.matchMedia(MOBILE_QUERY).matches,
        });
        this.handleResize = () => {
            this.state.isMobile = window.matchMedia(MOBILE_QUERY).matches;
        };
        this.handlePlannerKeydown = (event) => {
            const shouldHandleEscape = shouldHandlePlannerEscape({
                key: event.key,
                activeSection: this.state.activeSection,
                selectedCount: this.state.selectedMatchIds.length,
                hasPendingValidation: Boolean(this.state.pendingValidation),
            });
            if (!shouldHandleEscape) {
                return;
            }
            this.clearPlannerSelection();
            if (this.state.pendingValidation) {
                this.clearPendingValidation();
            }
            this.notify("Planner selection cleared.", "info");
        };

        onWillStart(async () => {
            await this.loadInitialData();
        });
        onMounted(() => {
            window.addEventListener("resize", this.handleResize);
            window.addEventListener("keydown", this.handlePlannerKeydown);
            if (typeof window !== "undefined") {
                this.heartbeatTimer = window.setInterval(() => {
                    this.refreshCollaboration({ silent: true });
                }, 45000);
            }
        });
        onWillUnmount(() => {
            window.removeEventListener("resize", this.handleResize);
            window.removeEventListener("keydown", this.handlePlannerKeydown);
            if (this.heartbeatTimer) {
                window.clearInterval(this.heartbeatTimer);
            }
        });
    }

    readPersistedUiState(params = {}) {
        if (typeof window === "undefined" || !window.localStorage) {
            return {};
        }
        try {
            const rawValue = window.localStorage.getItem(UI_STATE_STORAGE_KEY);
            if (!rawValue) {
                return {};
            }
            const parsedValue = JSON.parse(rawValue);
            if (!parsedValue || typeof parsedValue !== "object") {
                return {};
            }
            if (
                params.competition_id
                && parsedValue.competitionId
                && Number(parsedValue.competitionId) !== Number(params.competition_id)
            ) {
                return {};
            }
            return parsedValue;
        } catch {
            return {};
        }
    }

    persistUiState() {
        if (typeof window === "undefined" || !window.localStorage) {
            return;
        }
        const competitionId = this.state.currentCompetitionId || false;
        const divisionId = this.state.currentDivisionId || false;
        if (!competitionId && !divisionId) {
            window.localStorage.removeItem(UI_STATE_STORAGE_KEY);
            return;
        }
        window.localStorage.setItem(
            UI_STATE_STORAGE_KEY,
            JSON.stringify({
                activeSection: this.state.activeSection,
                competitionId,
                divisionId,
                filters: { ...this.state.filters },
                gamedayId: this.state.currentGamedayId || false,
            })
        );
    }

    async loadInitialData() {
        await this.loadWorkspace();
        if (this.state.activeSection === "teams") {
            await this.loadTeamSearchData();
        }
        if (
            this.state.activeSection === "planner"
            && !this.planner
            && (this.state.currentGamedayId || this.gamedayOptions[0]?.id)
        ) {
            await this.loadPlanner(
                Number(this.state.currentGamedayId || this.gamedayOptions[0].id),
                { silent: true }
            );
        }
    }

    get payload() {
        return this.state.payload || {};
    }

    get selectedDivision() {
        return this.payload.selected_division || false;
    }

    get planner() {
        return this.payload.planner || false;
    }

    get currentPlannerRevision() {
        return this.planner?.gameday?.planner_revision ?? false;
    }

    get currentPlannerState() {
        return this.planner?.gameday?.planner_state || "draft";
    }

    get workspaceSections() {
        return resolveWorkspaceSections({
            competition: this.payload.competition,
            division: this.selectedDivision,
        }).map((section) => ({
            ...section,
            active: section.key === this.state.activeSection,
        }));
    }
    get progressSteps() {
        return this.workspaceSections;
    }
    get activeWorkspaceSection() {
        return this.workspaceSections.find(
            (section) => section.key === this.state.activeSection
        ) || this.workspaceSections[0];
    }
    get recommendedWorkspaceSection() {
        return this.workspaceSections.find(
            (section) => !section.disabled && !section.complete
        ) || this.workspaceSections.filter((section) => !section.disabled).at(-1);
    }
    get previousWorkspaceSection() {
        const available = this.workspaceSections.filter((section) => !section.disabled);
        const index = available.findIndex(
            (section) => section.key === this.state.activeSection
        );
        return index > 0 ? available[index - 1] : false;
    }
    get nextWorkspaceSection() {
        const available = this.workspaceSections.filter((section) => !section.disabled);
        const index = available.findIndex(
            (section) => section.key === this.state.activeSection
        );
        return index >= 0 && index < available.length - 1
            ? available[index + 1]
            : false;
    }
    get divisionPlanningFormatOptions() {
        return DIVISION_PLANNING_FORMAT_OPTIONS;
    }

    get divisionCategoryOptions() {
        return DIVISION_CATEGORY_OPTIONS;
    }

    get divisionGenderOptions() {
        return DIVISION_GENDER_OPTIONS;
    }

    get divisionOptions() {
        return this.payload.divisions || [];
    }

    get gamedayOptions() {
        return this.selectedDivision?.gamedays || [];
    }

    get stageOptions() {
        return this.selectedDivision?.stage_options || [];
    }

    get sharedDivisionOptions() {
        return this.divisionOptions.filter(
            (division) => division.id !== this.state.currentDivisionId
        );
    }

    get selectedSharedDivisionOptions() {
        const selected = new Set(this.state.gamedayForm.sharedDivisionIds);
        return this.sharedDivisionOptions.filter((division) => selected.has(division.id));
    }

    getDivisionById(divisionId) {
        return this.divisionOptions.find((division) => Number(division.id) === Number(divisionId));
    }

    getSharedDivisionConfig(divisionId) {
        return this.state.gamedayForm.sharedDivisionConfig[String(divisionId)] || {
            stage_id: "",
            round_number: "",
        };
    }

    getSharedDivisionStageOptions(divisionId) {
        return this.getDivisionById(divisionId)?.stage_options || [];
    }

    getSharedDivisionRoundOptions(divisionId) {
        const division = this.getDivisionById(divisionId);
        if (!division) {
            return [];
        }
        const rounds = division.rounds || [];
        const stageId = Number(this.getSharedDivisionConfig(divisionId).stage_id || 0);
        if (!stageId) {
            return rounds;
        }
        return rounds.filter((roundItem) => Number(roundItem.stage_id) === stageId);
    }

    ensureSharedDivisionConfig(divisionId) {
        const key = String(divisionId);
        const current = this.getSharedDivisionConfig(divisionId);
        const stageOptions = this.getSharedDivisionStageOptions(divisionId);
        const selectedStageId = current.stage_id && stageOptions.some(
            (stage) => String(stage.id) === String(current.stage_id)
        )
            ? String(current.stage_id)
            : stageOptions[0]?.id
                ? String(stageOptions[0].id)
                : "";
        const roundOptions = this.getSharedDivisionRoundOptions(divisionId).filter(
            (roundItem) => !selectedStageId || String(roundItem.stage_id) === selectedStageId
        );
        const selectedRoundNumber = current.round_number && roundOptions.some(
            (roundItem) => String(roundItem.round_number) === String(current.round_number)
        )
            ? String(current.round_number)
            : roundOptions[0]?.round_number
                ? String(roundOptions[0].round_number)
                : "";

        this.state.gamedayForm.sharedDivisionConfig = {
            ...this.state.gamedayForm.sharedDivisionConfig,
            [key]: {
                stage_id: selectedStageId,
                round_number: selectedRoundNumber,
            },
        };
    }

    get roundOptions() {
        const rounds = this.selectedDivision?.rounds || [];
        const stageId = Number(
            this.planner?.gameday?.stage_id || this.state.gamedayForm.stage_id || 0
        );
        if (!stageId) {
            return rounds;
        }
        return rounds.filter((roundItem) => Number(roundItem.stage_id) === stageId);
    }

    get plannerDivisionOptions() {
        return this.planner?.participating_divisions || [];
    }

    get plannerTeamOptions() {
        return this.planner?.team_options || [];
    }

    get plannerDivisionSummary() {
        return this.plannerDivisionOptions.map((division) => division.name).join(" · ");
    }

    get plannerFairnessSummary() {
        return this.planner?.fairness_summary
            || this.selectedDivision?.fairness_summary
            || DEFAULT_FAIRNESS_SUMMARY;
    }

    get plannerPolicyBadge() {
        if (!this.selectedDivision) {
            return false;
        }
        const minimumRestMinutes = Math.max(
            Number(this.selectedDivision.minimum_rest_minutes || 0),
            0
        );
        const maxConsecutiveMatches = Math.max(
            Number(this.selectedDivision.max_consecutive_matches_per_team || 1),
            1
        );
        if (maxConsecutiveMatches <= 1) {
            return {
                className: "text-bg-success",
                label: "Strict no back-to-back",
                detail: minimumRestMinutes
                    ? `${minimumRestMinutes} min rest required between matches`
                    : "Back-to-back sequences are blocked by policy",
            };
        }
        return {
            className: "text-bg-warning",
            label: `Consecutive limit: ${maxConsecutiveMatches}`,
            detail: minimumRestMinutes
                ? `${minimumRestMinutes} min rest target for short-rest warnings`
                : "No minimum rest target configured",
        };
    }

    get slotSuggestions() {
        return this.state.slotSuggestions?.items || [];
    }

    get shouldShowSlotSuggestions() {
        return Boolean(
            this.selectedUnscheduledMatches.length === 1
                && !this.selectedAssignedMatches.length
        );
    }

    get generationPreview() {
        return this.selectedDivision?.generation_preview || DEFAULT_GENERATION_PREVIEW;
    }

    get generationSectionTitle() {
        return {
            single_round_robin: "Round-robin generation",
            double_round_robin: "Double round-robin generation",
            knockout: "Knockout generation",
            manual: "Manual planning",
            pool_then_bracket: "Pool then bracket planning",
        }[this.generationPreview.format] || "Schedule generation";
    }

    get generationActionLabel() {
        return this.generationPreview.action_label || "Generate schedule structure";
    }

    get workspaceCollaboration() {
        return this.state.collaboration.workspace || DEFAULT_COLLABORATION;
    }

    get plannerCollaboration() {
        return this.state.collaboration.planner || DEFAULT_COLLABORATION;
    }

    get plannerScheduleRevisions() {
        return this.planner?.gameday?.schedule_revisions || DEFAULT_SCHEDULE_REVISIONS;
    }

    get publishRequiresReason() {
        const hasWarnings = Boolean((this.activeValidation?.warnings || []).length);
        const hasLiveRevision = Boolean(
            this.plannerScheduleRevisions.live_revision
            || (this.selectedDivision?.gamedays || []).some(
                (gameday) => gameday.schedule_revisions?.live_revision
            )
        );
        return hasWarnings || hasLiveRevision;
    }

    get canCreateCompetitionShell() {
        return Boolean(this.state.shellForm.name.trim() && this.state.shellForm.season_id);
    }

    get plannerIssues() {
        return [
            ...(this.planner?.validation?.blocking || []),
            ...(this.planner?.validation?.warnings || []),
        ];
    }

    get plannerIssueMatchIds() {
        const matchIds = new Set();
        for (const issue of this.plannerIssues) {
            if (issue.match_id) {
                matchIds.add(issue.match_id);
            }
            if (issue.focus_target === "match" && issue.focus_record_id) {
                matchIds.add(issue.focus_record_id);
            }
        }
        return matchIds;
    }

    get plannerIssueTeamIds() {
        const teamIds = new Set();
        for (const issue of this.plannerIssues) {
            for (const teamId of issue.team_ids || []) {
                if (teamId) {
                    teamIds.add(teamId);
                }
            }
        }
        return teamIds;
    }

    get plannerIssueSlotIds() {
        const slotIds = new Set();
        for (const issue of this.plannerIssues) {
            if (issue.slot_id) {
                slotIds.add(issue.slot_id);
            }
            if (issue.focus_target === "slot" && issue.focus_record_id) {
                slotIds.add(issue.focus_record_id);
            }
        }
        return slotIds;
    }

    get plannerHighlightedMatchIds() {
        const matchIds = new Set(this.plannerIssueMatchIds);
        for (const match of this.plannerMatchMap.values()) {
            if (
                this.plannerIssueTeamIds.has(match.home_team_id)
                || this.plannerIssueTeamIds.has(match.away_team_id)
            ) {
                matchIds.add(match.id);
            }
        }
        return [...matchIds];
    }

    get plannerHighlightedSlotIds() {
        return [...this.plannerIssueSlotIds];
    }

    get plannerConflictIds() {
        return new Set(
            (this.planner?.validation?.blocking || [])
                .map((issue) => issue.record_id)
                .filter(Boolean)
        );
    }

    get filteredUnscheduledMatches() {
        let matches = this.planner?.unscheduled_matches || [];
        if (this.state.filters.roundNumber) {
            matches = matches.filter(
                (match) => String(match.round_number) === String(this.state.filters.roundNumber)
            );
        }
        if (this.state.filters.teamId) {
            matches = matches.filter(
                (match) => String(match.home_team_id) === String(this.state.filters.teamId)
                    || String(match.away_team_id) === String(this.state.filters.teamId)
            );
        }
        if (this.state.filters.divisionId) {
            matches = matches.filter(
                (match) => String(match.division_id) === String(this.state.filters.divisionId)
            );
        }
        if (this.state.filters.conflictsOnly) {
            matches = matches.filter((match) => this.plannerConflictIds.has(match.id));
        }
        return matches;
    }

    get plannerRows() {
        const rowMap = new Map();
        for (const slot of this.planner?.slots || []) {
            const key = `${slot.start_datetime}|${slot.end_datetime}`;
            if (!rowMap.has(key)) {
                rowMap.set(key, {
                    key,
                    startLabel: slot.start_label,
                    endLabel: slot.end_label,
                    cells: {},
                });
            }
            rowMap.get(key).cells[slot.court_id] = slot;
        }
        return [...rowMap.values()];
    }

    get mobileSlotOptions() {
        const selectedMatchId = Number(this.state.mobileAssign.match_id || 0);
        return (this.planner?.slots || []).filter(
            (slot) => ["available", "reserved"].includes(slot.state)
                || slot.match?.id === selectedMatchId
        );
    }

    get activeValidation() {
        return this.state.pendingValidation?.validation
            || this.state.validationSnapshot
            || this.selectedDivision?.validation
            || DEFAULT_VALIDATION;
    }

    get selectedMatchIdSet() {
        return new Set((this.state.selectedMatchIds || []).map((matchId) => Number(matchId)));
    }

    get assignedPlannerMatchIds() {
        return new Set(
            (this.planner?.slots || [])
                .map((slot) => slot.match?.id)
                .filter(Boolean)
        );
    }

    get plannerMatchMap() {
        const matches = new Map();
        for (const match of this.planner?.unscheduled_matches || []) {
            matches.set(match.id, match);
        }
        for (const slot of this.planner?.slots || []) {
            if (slot.match?.id) {
                matches.set(slot.match.id, slot.match);
            }
        }
        return matches;
    }

    get selectedPlannerMatches() {
        return this.state.selectedMatchIds
            .map((matchId) => this.plannerMatchMap.get(Number(matchId)))
            .filter(Boolean);
    }

    get selectedUnscheduledMatches() {
        return this.selectedPlannerMatches.filter(
            (match) => !this.assignedPlannerMatchIds.has(match.id)
        );
    }

    get selectedAssignedMatches() {
        return this.selectedPlannerMatches.filter(
            (match) => this.assignedPlannerMatchIds.has(match.id)
        );
    }

    get plannerAssignedMatchCount() {
        return (this.planner?.slots || []).reduce(
            (count, slot) => (slot.match?.id ? count + 1 : count),
            0
        );
    }

    get plannerOpenSlotCount() {
        return (this.planner?.slots || []).filter(
            (slot) => !slot.match && ["available", "reserved"].includes(slot.state)
        ).length;
    }

    get allFilteredMatchesSelected() {
        const filteredMatchIds = this.filteredUnscheduledMatches.map((match) => match.id);
        return Boolean(
            filteredMatchIds.length
            && filteredMatchIds.every((matchId) => this.selectedMatchIdSet.has(matchId))
        );
    }

    get hasMixedPlannerSelection() {
        return Boolean(
            this.selectedUnscheduledMatches.length && this.selectedAssignedMatches.length
        );
    }

    get plannerBusy() {
        return isPlannerBusyState({
            saving: this.state.saving,
            plannerLoading: this.state.plannerLoading,
            publishing: this.state.publishing,
        });
    }

    get plannerSelectionSummary() {
        return formatPlannerSelectionSummary({
            selectedCount: this.state.selectedMatchIds.length,
            unscheduledCount: this.selectedUnscheduledMatches.length,
            assignedCount: this.selectedAssignedMatches.length,
        });
    }

    get confirmationDialogToneClass() {
        if (this.state.confirmDialog.tone === "danger") {
            return "btn-danger";
        }
        if (this.state.confirmDialog.tone === "success") {
            return "btn-success";
        }
        return "btn-primary";
    }

    get canConfirmValidation() {
        return isPlannerValidationConfirmable({
            currentGamedayId: this.state.currentGamedayId,
            currentPlannerState: this.currentPlannerState,
            saving: this.state.saving,
            plannerLoading: this.state.plannerLoading,
            publishing: this.state.publishing,
        });
    }

    get canBulkAssignSelection() {
        return Boolean(
            this.selectedUnscheduledMatches.length
            && !this.selectedAssignedMatches.length
            && this.state.currentGamedayId
            && !this.plannerBusy
        );
    }

    get canBulkUnassignSelection() {
        return Boolean(
            this.selectedAssignedMatches.length
            && !this.selectedUnscheduledMatches.length
            && this.state.currentGamedayId
            && !this.plannerBusy
        );
    }

    get canUnassignAllMatches() {
        return Boolean(
            this.state.currentGamedayId
            && this.plannerAssignedMatchCount
            && !this.plannerBusy
        );
    }

    get canAutoSchedule() {
        return Boolean(
            this.state.currentGamedayId
            && (this.filteredUnscheduledMatches || []).length
            && this.plannerOpenSlotCount
            && !this.plannerBusy
        );
    }

    get pendingValidationTitle() {
        return this.state.pendingValidation?.title || "Assignment review";
    }

    get forcePendingLabel() {
        return this.state.pendingValidation?.action === "bulk_assign"
            ? "Force bulk assign"
            : "Force assignment";
    }

    get canForcePendingAction() {
        const validation = this.state.pendingValidation?.validation || DEFAULT_VALIDATION;
        return Boolean(
            this.state.pendingValidation?.allowForce
            && this.payload.capabilities?.can_force_assign
            && !(validation.blocking || []).length
            && (validation.warnings || []).length
        );
    }

}

applyPrototypeMethods(CompetitionWorkspaceAction.prototype, CompetitionWorkspacePlannerDataMethods);
applyPrototypeMethods(CompetitionWorkspaceAction.prototype, CompetitionWorkspaceFormMethods);
applyPrototypeMethods(CompetitionWorkspaceAction.prototype, CompetitionWorkspacePublishingMethods);
applyPrototypeMethods(CompetitionWorkspaceAction.prototype, CompetitionWorkspacePlannerActionMethods);

registry.category("actions").add(
    "sports_federation_competition_engine.competition_workspace",
    CompetitionWorkspaceAction
);
