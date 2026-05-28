/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";

const MOBILE_QUERY = "(max-width: 991.98px)";
const UI_STATE_STORAGE_KEY = "sports_federation_competition_engine.competition_workspace.ui_state";

export function isPlannerBusyState({ saving = false, plannerLoading = false, publishing = false } = {}) {
    return Boolean(saving || plannerLoading || publishing);
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

class StatusBadge extends Component {
    static template = "sports_federation_competition_engine.CompetitionWorkspaceStatusBadge";

    get badgeClass() {
        return badgeClass(this.props.tone || stateTone(this.props.state));
    }
}

class ProgressStepper extends Component {
    static template = "sports_federation_competition_engine.CompetitionWorkspaceProgressStepper";

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

    get progressSteps() {
        const division = this.selectedDivision;
        return [
            {
                key: "shell",
                label: "Competition",
                complete: !!this.payload.competition?.id,
                active: !this.payload.competition?.id,
            },
            {
                key: "entries",
                label: "Teams",
                complete: !!division?.entries_locked,
                active: !!division && !division.entries_locked,
            },
            {
                key: "rounds",
                label: "Rounds",
                complete: !!division?.match_count,
                active: !!division && division.entries_locked && !division.match_count,
            },
            {
                key: "gamedays",
                label: "Gamedays",
                complete: !!division?.gameday_count,
                active: !!division && division.match_count > 0 && !division.gameday_count,
            },
            {
                key: "planner",
                label: "Planner",
                complete: !!division && division.match_count > 0 && division.unscheduled_match_count === 0 && division.slot_count > 0,
                active: !!division && division.gameday_count > 0 && division.unscheduled_match_count > 0,
            },
            {
                key: "publish",
                label: "Publish",
                complete: division?.workspace_state === "published",
                active: !!division && division.unscheduled_match_count === 0 && division.workspace_state !== "published",
            },
        ];
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
        return this.planner?.fairness_summary || this.selectedDivision?.fairness_summary || {
            court_balance_gap_percent: 0,
            rest_balance_gap_minutes: 0,
            score_components: [],
            team_metrics: [],
            timeslot_balance_gap_minutes: 0,
            tracked_team_count: 0,
            warnings: [],
        };
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
        return this.selectedDivision?.generation_preview || {
            action_label: false,
            description: "",
            empty_message: "No generated preview is available yet.",
            format: false,
            rounds: [],
            supported: false,
        };
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
        return this.state.collaboration.workspace || {
            active_count: 0,
            active_users: [],
            same_gameday_count: 0,
            same_gameday_users: [],
            warning_message: false,
        };
    }

    get plannerCollaboration() {
        return this.state.collaboration.planner || {
            active_count: 0,
            active_users: [],
            same_gameday_count: 0,
            same_gameday_users: [],
            warning_message: false,
        };
    }

    get plannerScheduleRevisions() {
        return this.planner?.gameday?.schedule_revisions || {
            draft_revision: false,
            live_revision: false,
            recent_revisions: [],
        };
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
            || { blocking: [], warnings: [], unscheduled_matches: [], empty_slots: [] };
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
        return this.state.confirmDialog.tone === "danger" ? "btn-danger" : "btn-primary";
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
        const validation = this.state.pendingValidation?.validation || {
            blocking: [],
            warnings: [],
        };
        return Boolean(
            this.state.pendingValidation?.allowForce
            && this.payload.capabilities?.can_force_assign
            && !(validation.blocking || []).length
            && (validation.warnings || []).length
        );
    }

    syncPlannerSelection(planner = this.planner) {
        const validMatchIds = new Set();
        for (const match of planner?.unscheduled_matches || []) {
            validMatchIds.add(match.id);
        }
        for (const slot of planner?.slots || []) {
            if (slot.match?.id) {
                validMatchIds.add(slot.match.id);
            }
        }
        this.state.selectedMatchIds = (this.state.selectedMatchIds || []).filter((matchId) =>
            validMatchIds.has(Number(matchId))
        );
    }

    clearPlannerSelection() {
        this.state.selectedMatchIds = [];
        this.state.slotSuggestions = {
            items: [],
            loading: false,
            matchId: false,
        };
    }

    resetPlannerPagination() {
        this.state.plannerUnscheduledLimit = this.state.plannerPageSize;
    }

    resetPlannerFilters() {
        this.state.filters.divisionId = "";
        this.state.filters.roundNumber = "";
        this.state.filters.teamId = "";
        this.state.filters.conflictsOnly = false;
    }

    buildPlannerRpcFilters({ includeReferenceData = true, unscheduledLimit } = {}) {
        return {
            division_id: this.state.filters.divisionId || false,
            conflicts_only: this.state.filters.conflictsOnly,
            include_reference_data: includeReferenceData,
            round_number: this.state.filters.roundNumber || false,
            team_id: this.state.filters.teamId || false,
            unscheduled_limit: unscheduledLimit || this.state.plannerUnscheduledLimit,
        };
    }

    toggleMatchSelection(matchId) {
        const selectedMatchIds = new Set(this.state.selectedMatchIds || []);
        if (selectedMatchIds.has(matchId)) {
            selectedMatchIds.delete(matchId);
        } else {
            selectedMatchIds.add(matchId);
        }
        this.state.selectedMatchIds = [...selectedMatchIds];
        this.refreshSlotSuggestions();
    }

    toggleFilteredSelection() {
        const filteredMatchIds = this.filteredUnscheduledMatches.map((match) => match.id);
        if (!filteredMatchIds.length) {
            return;
        }
        const selectedMatchIds = new Set(this.state.selectedMatchIds || []);
        const allSelected = filteredMatchIds.every((matchId) => selectedMatchIds.has(matchId));
        for (const matchId of filteredMatchIds) {
            if (allSelected) {
                selectedMatchIds.delete(matchId);
            } else {
                selectedMatchIds.add(matchId);
            }
        }
        this.state.selectedMatchIds = [...selectedMatchIds];
        this.refreshSlotSuggestions();
    }

    async refreshSlotSuggestions() {
        if (!this.state.currentGamedayId || !this.shouldShowSlotSuggestions) {
            this.state.slotSuggestions = {
                items: [],
                loading: false,
                matchId: false,
            };
            return false;
        }

        const match = this.selectedUnscheduledMatches[0];
        this.state.slotSuggestions = {
            items: [],
            loading: true,
            matchId: match.id,
        };
        try {
            const suggestions = await this.orm.call(
                "federation.competition.workspace.service",
                "get_match_slot_suggestions",
                [match.id, this.state.currentGamedayId, 5]
            );
            if (this.state.slotSuggestions.matchId !== match.id) {
                return false;
            }
            this.state.slotSuggestions = {
                items: suggestions,
                loading: false,
                matchId: match.id,
            };
            return suggestions;
        } catch (error) {
            this.state.slotSuggestions = {
                items: [],
                loading: false,
                matchId: false,
            };
            this.notify(error.message || "Slot suggestions could not be loaded.", "warning");
            return false;
        }
    }

    async loadWorkspace({
        competitionId = this.state.currentCompetitionId,
        divisionId = this.state.currentDivisionId,
        gamedayId = this.state.currentGamedayId,
        includePlanner = Boolean(gamedayId),
        includePlannerReferenceData,
        unscheduledLimit,
    } = {}) {
        this.state.loading = true;
        this.state.error = null;
        try {
            const requestedGamedayId = gamedayId || false;
            const samePlannerTarget = Boolean(
                requestedGamedayId
                && this.planner?.gameday?.id
                && Number(this.planner.gameday.id) === Number(requestedGamedayId)
            );
            const resolvedIncludePlannerReferenceData = includePlannerReferenceData
                ?? !samePlannerTarget;
            const payload = await this.orm.call(
                "federation.competition.workspace.service",
                "get_competition_workspace_data",
                [competitionId || false, divisionId || false, {
                    gameday_id: requestedGamedayId,
                    include_planner: includePlanner,
                    include_planner_reference_data: resolvedIncludePlannerReferenceData,
                    planner_filters: requestedGamedayId
                        ? this.buildPlannerRpcFilters({
                            includeReferenceData: resolvedIncludePlannerReferenceData,
                            unscheduledLimit,
                        })
                        : false,
                }]
            );
            if (
                payload.planner
                && !resolvedIncludePlannerReferenceData
                && this.state.payload?.planner
            ) {
                payload.planner = {
                    ...this.state.payload.planner,
                    ...payload.planner,
                };
            }
            this.state.payload = payload;
            this.state.currentCompetitionId = payload.competition?.id || competitionId || false;
            this.state.currentDivisionId = payload.selected_division_id || divisionId || false;
            const resolvedRequestedGamedayId = payload.selected_division?.gamedays?.some(
                (day) => day.id === gamedayId
            )
                ? gamedayId
                : false;
            this.state.currentGamedayId = payload.planner?.gameday?.id
                || resolvedRequestedGamedayId
                || payload.selected_division?.gamedays?.[0]?.id
                || false;
            this.syncPlannerSelection(payload.planner);
            const stageOptions = payload.selected_division?.stage_options || [];
            if (stageOptions.length) {
                const defaultStageId = payload.planner?.gameday?.stage_id || stageOptions[0].id;
                const selectedStageId = String(this.state.gamedayForm.stage_id || "");
                if (!stageOptions.some((stage) => String(stage.id) === selectedStageId)) {
                    this.state.gamedayForm.stage_id = String(defaultStageId);
                }
            } else {
                this.state.gamedayForm.stage_id = "";
            }
            if (unscheduledLimit) {
                this.state.plannerUnscheduledLimit = unscheduledLimit;
            }
            if (resolvedRequestedGamedayId && !payload.planner) {
                await this.loadPlanner(resolvedRequestedGamedayId, {
                    includeReferenceData: resolvedIncludePlannerReferenceData,
                    silent: true,
                    unscheduledLimit,
                });
            }
            await this.loadCourtsForVenue(this.state.gamedayForm.venue_id || payload.planner?.gameday?.venue_id || false);
            await this.refreshCollaboration({
                activeSection: this.state.activeSection,
                competitionId: this.state.currentCompetitionId,
                divisionId: this.state.currentDivisionId,
                gamedayId: this.state.currentGamedayId,
                silent: true,
            });
            await this.refreshSlotSuggestions();
            this.persistUiState();
        } catch (error) {
            this.state.error = error.message || "The workspace could not be loaded.";
        } finally {
            this.state.loading = false;
        }
    }

    async loadPlanner(
        gamedayId,
        { silent = false, includeReferenceData, unscheduledLimit } = {}
    ) {
        if (!gamedayId) {
            return false;
        }
        if (!silent) {
            this.state.plannerLoading = true;
        }
        try {
            const requestedLimit = unscheduledLimit || this.state.plannerUnscheduledLimit;
            const samePlannerTarget = Boolean(
                this.planner?.gameday?.id
                && Number(this.planner.gameday.id) === Number(gamedayId)
            );
            const resolvedIncludeReferenceData = includeReferenceData ?? !samePlannerTarget;
            const planner = await this.orm.call(
                "federation.competition.workspace.service",
                "get_gameday_planner_data",
                [
                    gamedayId,
                    this.buildPlannerRpcFilters({
                        includeReferenceData: resolvedIncludeReferenceData,
                        unscheduledLimit: requestedLimit,
                    }),
                ]
            );
            const nextPlanner = !resolvedIncludeReferenceData && this.state.payload?.planner
                ? {
                    ...this.state.payload.planner,
                    ...planner,
                }
                : planner;
            if (this.state.payload) {
                this.state.payload.planner = nextPlanner;
            }
            this.state.currentGamedayId = nextPlanner.gameday.id;
            this.state.gamedayForm.selected_gameday_id = String(nextPlanner.gameday.id);
            this.state.gamedayForm.stage_id = nextPlanner.gameday.stage_id
                ? String(nextPlanner.gameday.stage_id)
                : "";
            this.state.gamedayForm.round_number = nextPlanner.gameday.sequence
                ? String(nextPlanner.gameday.sequence)
                : "";
            this.state.plannerUnscheduledLimit = requestedLimit;
            if (nextPlanner.gameday.venue_id) {
                this.state.gamedayForm.venue_id = String(nextPlanner.gameday.venue_id);
                await this.loadCourtsForVenue(nextPlanner.gameday.venue_id);
            }
            this.syncPlannerSelection(nextPlanner);
            await this.refreshCollaboration({
                activeSection: this.state.activeSection,
                competitionId: this.state.currentCompetitionId,
                divisionId: this.state.currentDivisionId,
                gamedayId: nextPlanner.gameday.id,
                silent: true,
            });
            await this.refreshSlotSuggestions();
            this.persistUiState();
            return nextPlanner;
        } catch (error) {
            this.notify(error.message || "The planner could not be refreshed.", "danger");
            return false;
        } finally {
            this.state.plannerLoading = false;
        }
    }

    async loadAvailableClubs() {
        this.state.availableClubs = await this.orm.searchRead(
            "federation.club",
            [],
            ["display_name"],
            { order: "name asc" }
        );
    }

    async loadTeamSearchData() {
        if (!this.state.currentDivisionId) {
            this.state.availableTeams = [];
            return;
        }
        this.state.teamSearchLoading = true;
        try {
            if (!this.state.availableClubs.length) {
                await this.loadAvailableClubs();
            }
            this.state.availableTeams = await this.orm.call(
                "federation.competition.workspace.service",
                "search_available_teams",
                [this.state.currentDivisionId, {
                    club_id: this.state.teamEntryForm.club_id
                        ? Number(this.state.teamEntryForm.club_id)
                        : false,
                    limit: 40,
                    query: this.state.teamEntryForm.search || false,
                }]
            );
        } catch (error) {
            this.notify(error.message || "Team search could not be refreshed.", "danger");
        } finally {
            this.state.teamSearchLoading = false;
        }
    }

    async loadCourtsForVenue(venueId) {
        if (!venueId) {
            this.state.availableCourts = [];
            return;
        }
        this.state.availableCourts = await this.orm.searchRead(
            "federation.playing.area",
            [["venue_id", "=", Number(venueId)]],
            ["display_name", "venue_id"],
            { order: "name asc" }
        );
    }

    async refreshCollaboration({
        competitionId = this.state.currentCompetitionId,
        divisionId = this.state.currentDivisionId,
        gamedayId = this.state.currentGamedayId,
        activeSection = this.state.activeSection,
        silent = true,
    } = {}) {
        if (!competitionId && !divisionId) {
            this.state.collaboration.workspace = false;
            this.state.collaboration.planner = false;
            return false;
        }
        try {
            const summary = await this.orm.call(
                "federation.competition.workspace.service",
                "heartbeat_workspace_presence",
                [competitionId || false, divisionId || false, gamedayId || false, activeSection || "overview"]
            );
            this.state.collaboration.workspace = summary.workspace_collaboration || false;
            this.state.collaboration.planner = summary.planner_collaboration || false;
            return summary;
        } catch (error) {
            if (!silent) {
                this.notify(
                    error.message || "Workspace collaboration status could not be refreshed.",
                    "warning"
                );
            }
            return false;
        }
    }

    notify(message, type = "info") {
        this.notification.add(message, { type });
    }

    setSection(section) {
        this.state.activeSection = section;
        if (section === "planner" && (this.state.currentGamedayId || this.gamedayOptions[0]?.id)) {
            this.loadPlanner(this.state.currentGamedayId || this.gamedayOptions[0].id, {
                includeReferenceData: !this.planner,
                silent: true,
            });
        }
        if (section === "teams") {
            this.loadTeamSearchData();
        }
        this.refreshCollaboration({
            activeSection: section,
            silent: true,
        });
        this.persistUiState();
    }

    updateShellField(ev) {
        this.state.shellForm[ev.target.name] = ev.target.value;
    }

    updateDivisionField(ev) {
        this.state.divisionForm[ev.target.name] = ev.target.value;
        if (ev.target.name === "planning_format" && ev.target.value !== "pool_then_bracket") {
            this.state.divisionForm.pool_count = "2";
            this.state.divisionForm.pool_qualifier_count = "2";
        }
    }

    async updateTeamEntryField(ev) {
        this.state.teamEntryForm[ev.target.name] = ev.target.value;
        if (["club_id", "search"].includes(ev.target.name)) {
            this.state.teamEntryForm.team_id = "";
            await this.loadTeamSearchData();
        }
    }

    async updateGamedayField(ev) {
        this.state.gamedayForm[ev.target.name] = ev.target.value;
        if (ev.target.name === "venue_id") {
            this.state.gamedayForm.courtIds = [];
            await this.loadCourtsForVenue(ev.target.value);
        }
    }

    updateFilterField(ev) {
        const name = ev.target.name;
        this.state.filters[name] = ev.target.type === "checkbox" ? ev.target.checked : ev.target.value;
        this.clearPlannerSelection();
        this.resetPlannerPagination();
        this.persistUiState();
        if (this.state.currentGamedayId) {
            this.loadPlanner(this.state.currentGamedayId, {
                includeReferenceData: false,
                silent: true,
            });
        }
    }

    async updateMobileAssignField(ev) {
        this.state.mobileAssign[ev.target.name] = ev.target.value;
        if (ev.target.name === "gameday_id") {
            this.state.mobileAssign.slot_id = "";
            await this.loadPlanner(Number(ev.target.value), { silent: true });
        }
    }

    async updateDivisionPlanningRule(ev) {
        if (!this.state.currentDivisionId) {
            return;
        }
        const fieldName = ev.target.name;
        if (!["minimum_rest_minutes", "max_consecutive_matches_per_team"].includes(fieldName)) {
            return;
        }
        const rawValue = Number(ev.target.value || 0);
        const normalizedValue = fieldName === "minimum_rest_minutes"
            ? Math.max(rawValue, 0)
            : Math.max(rawValue || 1, 1);
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "update_division_planning_rules",
                [this.state.currentDivisionId, { [fieldName]: normalizedValue }]
            );
            this.state.payload = result.payload;
            this.notify("Planning rules updated.", "success");
        } catch (error) {
            this.notify(error.message || "Planning rules could not be updated.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    updatePendingOverrideReason(ev) {
        this.state.overrideReason.pending = ev.target.value;
    }

    updatePublishOverrideReason(ev) {
        this.state.overrideReason.publish = ev.target.value;
    }

    toggleCourt(ev) {
        const courtId = Number(ev.target.value);
        const selected = new Set(this.state.gamedayForm.courtIds);
        if (ev.target.checked) {
            selected.add(courtId);
        } else {
            selected.delete(courtId);
        }
        this.state.gamedayForm.courtIds = [...selected];
    }

    toggleSharedDivision(ev) {
        const divisionId = Number(ev.target.value);
        const selected = new Set(this.state.gamedayForm.sharedDivisionIds);
        const config = { ...this.state.gamedayForm.sharedDivisionConfig };
        if (ev.target.checked) {
            selected.add(divisionId);
            this.state.gamedayForm.sharedDivisionIds = [...selected];
            this.state.gamedayForm.sharedDivisionConfig = config;
            this.ensureSharedDivisionConfig(divisionId);
            return;
        } else {
            selected.delete(divisionId);
            delete config[String(divisionId)];
        }
        this.state.gamedayForm.sharedDivisionIds = [...selected];
        this.state.gamedayForm.sharedDivisionConfig = config;
    }

    updateSharedDivisionConfig(ev) {
        const divisionId = String(ev.target.dataset.divisionId || "");
        const fieldName = ev.target.name;
        if (!divisionId || !fieldName) {
            return;
        }
        const existingConfig = this.getSharedDivisionConfig(divisionId);
        const nextConfig = {
            ...existingConfig,
            [fieldName]: ev.target.value,
        };
        if (fieldName === "stage_id") {
            const roundOptions = this.getSharedDivisionRoundOptions(divisionId).filter(
                (roundItem) => String(roundItem.stage_id) === String(ev.target.value || "")
            );
            if (!roundOptions.some(
                (roundItem) => String(roundItem.round_number) === String(nextConfig.round_number)
            )) {
                nextConfig.round_number = roundOptions[0]?.round_number
                    ? String(roundOptions[0].round_number)
                    : "";
            }
        }
        this.state.gamedayForm.sharedDivisionConfig = {
            ...this.state.gamedayForm.sharedDivisionConfig,
            [divisionId]: nextConfig,
        };
    }

    async createCompetitionShell() {
        const name = this.state.shellForm.name.trim();
        const seasonId = this.state.shellForm.season_id
            ? Number(this.state.shellForm.season_id)
            : false;
        if (!name || !seasonId) {
            this.notify("Provide a competition name and a season before creating it.", "warning");
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "create_competition_shell",
                [{
                    competition_id: this.state.shellForm.competition_id ? Number(this.state.shellForm.competition_id) : false,
                    competition_vals: this.state.shellForm.competition_id ? {} : {
                        name,
                        competition_type: this.state.shellForm.competition_type,
                    },
                    date_end: this.state.shellForm.date_end || false,
                    date_start: this.state.shellForm.date_start || false,
                    name,
                    season_id: seasonId,
                }]
            );
            this.state.currentCompetitionId = result.competition_id;
            this.state.payload = result.payload;
            this.state.currentDivisionId = result.payload.selected_division_id || false;
            this.state.currentGamedayId = false;
            this.persistUiState();
            this.notify("Competition created.", "success");
        } catch (error) {
            this.notify(error.message || "The competition could not be created.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async createDivision() {
        if (!this.state.currentCompetitionId) {
            return;
        }
        this.state.saving = true;
        try {
            const vals = {
                category: this.state.divisionForm.category || false,
                date_end: this.state.divisionForm.date_end || false,
                date_start: this.state.divisionForm.date_start || false,
                gender: this.state.divisionForm.gender || false,
                max_consecutive_matches_per_team: Number(
                    this.state.divisionForm.max_consecutive_matches_per_team || 1
                ),
                minimum_rest_minutes: Number(this.state.divisionForm.minimum_rest_minutes || 30),
                name: this.state.divisionForm.name,
                planning_format: this.state.divisionForm.planning_format,
            };
            if (this.state.divisionForm.planning_format === "pool_then_bracket") {
                vals.pool_count = Number(this.state.divisionForm.pool_count || 2);
                vals.pool_qualifier_count = Number(
                    this.state.divisionForm.pool_qualifier_count || 2
                );
            }
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "create_division",
                [this.state.currentCompetitionId, vals]
            );
            this.state.payload = result.payload;
            this.state.currentDivisionId = result.division_id;
            this.state.currentGamedayId = false;
            this.persistUiState();
            if (this.state.activeSection === "teams") {
                await this.loadTeamSearchData();
            }
            this.notify("Division created.", "success");
        } catch (error) {
            this.notify(error.message || "The division could not be created.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async createTeamEntry() {
        if (!this.state.currentDivisionId || !this.state.teamEntryForm.team_id) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "create_team_entry",
                [this.state.currentDivisionId, {
                    seed: this.state.teamEntryForm.seed ? Number(this.state.teamEntryForm.seed) : false,
                    team_id: Number(this.state.teamEntryForm.team_id),
                }]
            );
            this.state.payload = result.payload;
            this.state.teamEntryForm.club_id = "";
            this.state.teamEntryForm.search = "";
            this.state.teamEntryForm.seed = "";
            this.state.teamEntryForm.team_id = "";
            await this.loadTeamSearchData();
            this.notify("Team entry added.", "success");
        } catch (error) {
            this.notify(error.message || "The team entry could not be created.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async confirmTeamEntry(ev) {
        const entryId = Number(ev.currentTarget.dataset.entryId);
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "confirm_team_entry",
                [entryId]
            );
            this.state.payload = result.payload;
            this.notify("Team entry confirmed.", "success");
        } catch (error) {
            this.notify(error.message || "The team entry could not be confirmed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async lockEntries() {
        if (!this.state.currentDivisionId) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "lock_team_entries",
                [this.state.currentCompetitionId || false, this.state.currentDivisionId]
            );
            this.state.payload = result.payload;
            this.notify("Participant list locked.", "success");
        } catch (error) {
            this.notify(error.message || "The participant list could not be locked.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async generateScheduleStructure() {
        if (!this.state.currentDivisionId) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "generate_schedule_structure",
                [this.state.currentDivisionId, false]
            );
            this.state.payload = result.payload;
            this.notify(`${result.match_count} match(es) generated.`, "success");
        } catch (error) {
            this.notify(error.message || "Schedule generation failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async generateRoundRobin() {
        await this.generateScheduleStructure();
    }

    async createGameday() {
        if (!this.state.currentDivisionId || !this.state.gamedayForm.round_date) {
            return;
        }
        this.state.saving = true;
        try {
            const sharedStageIds = {};
            const sharedRoundNumbers = {};
            for (const divisionId of this.state.gamedayForm.sharedDivisionIds) {
                const config = this.getSharedDivisionConfig(divisionId);
                if (config.stage_id) {
                    sharedStageIds[String(divisionId)] = Number(config.stage_id);
                }
                if (config.round_number) {
                    sharedRoundNumbers[String(divisionId)] = Number(config.round_number);
                }
            }
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "create_gameday",
                [{
                    division_id: this.state.currentDivisionId,
                    name: this.state.gamedayForm.name || false,
                    round_number: this.state.gamedayForm.round_number
                        ? Number(this.state.gamedayForm.round_number)
                        : false,
                    round_date: this.state.gamedayForm.round_date,
                    shared_division_ids: this.state.gamedayForm.sharedDivisionIds,
                    shared_round_numbers: sharedRoundNumbers,
                    shared_stage_ids: sharedStageIds,
                    stage_id: this.state.gamedayForm.stage_id
                        ? Number(this.state.gamedayForm.stage_id)
                        : false,
                    venue_id: this.state.gamedayForm.venue_id ? Number(this.state.gamedayForm.venue_id) : false,
                }]
            );
            this.state.payload = result.payload;
            this.state.currentGamedayId = result.gameday_id;
            this.state.gamedayForm.selected_gameday_id = String(result.gameday_id);
            this.state.gamedayForm.sharedDivisionIds = [];
            this.state.gamedayForm.sharedDivisionConfig = {};
            this.resetPlannerFilters();
            this.resetPlannerPagination();
            this.persistUiState();
            this.notify("Gameday created.", "success");
            await this.loadPlanner(result.gameday_id);
        } catch (error) {
            this.notify(error.message || "The gameday could not be created.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async generateSlots() {
        const gamedayId = Number(this.state.gamedayForm.selected_gameday_id || this.state.currentGamedayId || 0);
        if (!gamedayId || !this.state.gamedayForm.courtIds.length) {
            return;
        }
        this.state.saving = true;
        try {
            const expectedPlannerRevision = this.planner?.gameday?.planner_revision ?? false;
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "generate_slots",
                [
                    gamedayId,
                    this.state.gamedayForm.courtIds,
                    this.state.gamedayForm.start_time,
                    this.state.gamedayForm.end_time,
                    Number(this.state.gamedayForm.match_duration_minutes || 35),
                    Number(this.state.gamedayForm.buffer_minutes || 5),
                    [],
                    false,
                    expectedPlannerRevision,
                ]
            );
            await this.loadWorkspace({
                competitionId: this.state.currentCompetitionId,
                divisionId: this.state.currentDivisionId,
                gamedayId,
            });
            this.notify(`${result.slot_count} slot(s) generated.`, "success");
        } catch (error) {
            this.notify(error.message || "Slot generation failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async selectDivision(ev) {
        const divisionId = Number(ev.currentTarget.dataset.divisionId || 0);
        this.state.currentDivisionId = divisionId;
        this.state.currentGamedayId = false;
        this.resetPlannerFilters();
        this.state.gamedayForm.sharedDivisionIds = [];
        this.state.gamedayForm.sharedDivisionConfig = {};
        this.state.gamedayForm.round_number = "";
        this.state.gamedayForm.stage_id = "";
        this.clearPlannerSelection();
        this.clearPendingValidation();
        this.resetPlannerPagination();
        await this.loadWorkspace({
            competitionId: this.state.currentCompetitionId,
            divisionId,
            gamedayId: false,
        });
        if (this.state.activeSection === "teams") {
            await this.loadTeamSearchData();
        }
    }

    async selectGameday(ev) {
        const gamedayId = Number(ev.currentTarget.dataset.gamedayId || 0);
        this.clearPlannerSelection();
        this.clearPendingValidation();
        this.resetPlannerFilters();
        this.resetPlannerPagination();
        await this.loadPlanner(gamedayId);
    }

    async loadMoreUnscheduledMatches() {
        if (!this.planner?.unscheduled_has_more || !this.state.currentGamedayId) {
            return;
        }
        const nextLimit = this.state.plannerUnscheduledLimit + this.state.plannerPageSize;
        await this.loadPlanner(this.state.currentGamedayId, {
            includeReferenceData: false,
            unscheduledLimit: nextLimit,
        });
    }

    async validateSchedule() {
        if (!this.state.currentCompetitionId && !this.state.currentDivisionId) {
            return;
        }
        try {
            this.state.validationSnapshot = await this.orm.call(
                "federation.competition.workspace.service",
                "validate_competition_schedule",
                [this.state.currentCompetitionId || false, this.state.currentDivisionId || false]
            );
            this.notify("Schedule validation refreshed.", "info");
        } catch (error) {
            this.notify(error.message || "Schedule validation failed.", "danger");
        }
    }

    openConfirmDialog({ action, title, message, confirmLabel = "Confirm", tone = "primary" }) {
        this.state.confirmDialog = {
            action,
            confirmLabel,
            message,
            open: true,
            title,
            tone,
        };
    }

    closeConfirmDialog() {
        this.state.confirmDialog = {
            action: false,
            confirmLabel: "Confirm",
            message: "",
            open: false,
            title: "Please confirm",
            tone: "primary",
        };
    }

    async confirmPendingAction() {
        const action = this.state.confirmDialog.action;
        this.closeConfirmDialog();
        if (action === "publish_gameday") {
            await this.publishGameday();
            return;
        }
        if (action === "publish_competition") {
            await this.publishCompetition();
            return;
        }
        if (action === "unassign_all") {
            await this.unassignAllMatches();
        }
    }

    requestPublishGameday() {
        if (!this.state.currentGamedayId || this.state.publishing) {
            return;
        }
        this.openConfirmDialog({
            action: "publish_gameday",
            title: "Publish gameday",
            message: "Publish this gameday and lock routine edits?",
            confirmLabel: "Publish gameday",
            tone: "primary",
        });
    }

    requestPublishCompetition() {
        if (this.state.publishing) {
            return;
        }
        this.openConfirmDialog({
            action: "publish_competition",
            title: "Publish competition",
            message: "Publish the competition schedule and lock routine edits?",
            confirmLabel: "Publish competition",
            tone: "primary",
        });
    }

    async publishGameday() {
        if (!this.state.currentGamedayId) {
            return;
        }
        this.state.publishing = true;
        try {
            const expectedPlannerRevision = this.planner?.gameday?.planner_revision ?? false;
            const overrideReason = this.state.overrideReason.publish.trim();
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "publish_gameday",
                [this.state.currentGamedayId, expectedPlannerRevision, overrideReason || false]
            );
            if (!result.ok) {
                this.state.validationSnapshot = result.validation;
                this.notify("The gameday still has blocking issues.", "warning");
                return;
            }
            this.state.payload = result.payload;
            this.state.overrideReason.publish = "";
            this.notify("Gameday published.", "success");
        } catch (error) {
            this.notify(error.message || "The gameday could not be published.", "danger");
        } finally {
            this.state.publishing = false;
        }
    }

    async publishCompetition() {
        if (!this.state.currentCompetitionId && !this.state.currentDivisionId) {
            return;
        }
        this.state.publishing = true;
        try {
            const overrideReason = this.state.overrideReason.publish.trim();
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "publish_competition_schedule",
                [
                    this.state.currentCompetitionId || false,
                    this.state.currentDivisionId || false,
                    overrideReason || false,
                ]
            );
            if (!result.ok) {
                this.state.validationSnapshot = result.validation;
                this.notify("The schedule still has blocking issues.", "warning");
                return;
            }
            this.state.payload = result.payload;
            this.state.overrideReason.publish = "";
            this.notify("Competition schedule published.", "success");
        } catch (error) {
            this.notify(error.message || "The competition schedule could not be published.", "danger");
        } finally {
            this.state.publishing = false;
        }
    }

    onDragStartMatch(matchId) {
        this.state.mobileAssign.match_id = String(matchId);
    }

    async assignMatch(matchId, slotId, force = false, overrideReason = false) {
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const resolvedOverrideReason = overrideReason || (force
                ? this.state.overrideReason.pending.trim()
                : false);
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "assign_match_to_slot",
                [
                    matchId,
                    slotId,
                    force,
                    this.currentPlannerRevision,
                    resolvedOverrideReason || false,
                ]
            );
            if (!result.ok) {
                if (!force) {
                    this.state.overrideReason.pending = "";
                }
                this.state.pendingValidation = {
                    action: "assign",
                    allowForce: true,
                    matchId,
                    slotId,
                    title: "Assignment review",
                    validation: result.validation,
                };
                this.notify("Assignment needs attention before it can be saved.", "warning");
                return;
            }
            this.state.pendingValidation = null;
            this.state.overrideReason.pending = "";
            this.clearPlannerSelection();
            await this.loadWorkspace({
                competitionId: this.state.currentCompetitionId,
                divisionId: this.state.currentDivisionId,
                gamedayId: this.state.currentGamedayId,
                includePlannerReferenceData: false,
                unscheduledLimit: this.state.plannerUnscheduledLimit,
            });
            this.notify("Match assignment saved.", "success");
        } catch (error) {
            this.notify(error.message || "The match could not be assigned.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async unassignMatch(matchId) {
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call(
                "federation.competition.workspace.service",
                "unassign_match",
                [matchId, this.currentPlannerRevision]
            );
            this.clearPlannerSelection();
            this.state.pendingValidation = null;
            await this.loadWorkspace({
                competitionId: this.state.currentCompetitionId,
                divisionId: this.state.currentDivisionId,
                gamedayId: this.state.currentGamedayId,
                includePlannerReferenceData: false,
                unscheduledLimit: this.state.plannerUnscheduledLimit,
            });
            this.notify("Match unassigned.", "success");
        } catch (error) {
            this.notify(error.message || "The match could not be unassigned.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async handleDropMatch(matchId, slotId) {
        await this.assignMatch(matchId, slotId, false);
    }

    async bulkAssignMatches(matchIds, force = false, overrideReason = false) {
        if (!this.state.currentGamedayId || !matchIds.length) {
            return;
        }
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const resolvedOverrideReason = overrideReason || (force
                ? this.state.overrideReason.pending.trim()
                : false);
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "bulk_assign_matches",
                [
                    this.state.currentGamedayId,
                    matchIds,
                    force,
                    this.currentPlannerRevision,
                    resolvedOverrideReason || false,
                ]
            );
            if (!result.ok) {
                if (!force) {
                    this.state.overrideReason.pending = "";
                }
                this.state.pendingValidation = {
                    action: "bulk_assign",
                    allowForce: true,
                    matchIds: [...matchIds],
                    title: "Bulk assignment review",
                    validation: result.validation,
                };
                this.notify("Bulk assignment needs attention before it can be saved.", "warning");
                return;
            }
            this.clearPlannerSelection();
            this.state.pendingValidation = null;
            this.state.overrideReason.pending = "";
            await this.loadWorkspace({
                competitionId: this.state.currentCompetitionId,
                divisionId: this.state.currentDivisionId,
                gamedayId: this.state.currentGamedayId,
                includePlannerReferenceData: false,
                unscheduledLimit: this.state.plannerUnscheduledLimit,
            });
            this.notify(`${result.operation_count || matchIds.length} match(es) assigned.`, "success");
        } catch (error) {
            this.notify(error.message || "Bulk assignment failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async bulkAssignSelected() {
        if (this.hasMixedPlannerSelection) {
            this.notify(
                "Select only unscheduled matches or only scheduled matches before using a bulk action.",
                "warning"
            );
            return;
        }
        await this.bulkAssignMatches(this.selectedUnscheduledMatches.map((match) => match.id), false);
    }

    async bulkUnassignSelected() {
        if (this.hasMixedPlannerSelection) {
            this.notify(
                "Select only unscheduled matches or only scheduled matches before using a bulk action.",
                "warning"
            );
            return;
        }
        const matchIds = this.selectedAssignedMatches.map((match) => match.id);
        if (!this.state.currentGamedayId || !matchIds.length) {
            return;
        }
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "bulk_unassign_matches",
                [this.state.currentGamedayId, matchIds, this.currentPlannerRevision]
            );
            if (!result.ok) {
                this.state.pendingValidation = {
                    action: "bulk_unassign",
                    allowForce: false,
                    matchIds: [...matchIds],
                    title: "Bulk unassignment review",
                    validation: result.validation,
                };
                this.notify("Bulk unassignment could not be completed.", "warning");
                return;
            }
            this.clearPlannerSelection();
            this.state.pendingValidation = null;
            await this.loadWorkspace({
                competitionId: this.state.currentCompetitionId,
                divisionId: this.state.currentDivisionId,
                gamedayId: this.state.currentGamedayId,
                includePlannerReferenceData: false,
                unscheduledLimit: this.state.plannerUnscheduledLimit,
            });
            this.notify(`${result.operation_count || matchIds.length} match(es) unassigned.`, "success");
        } catch (error) {
            this.notify(error.message || "Bulk unassignment failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    requestUnassignAllMatches() {
        if (!this.state.currentGamedayId || !this.plannerAssignedMatchCount) {
            return;
        }
        if (this.state.saving) {
            return;
        }
        this.openConfirmDialog({
            action: "unassign_all",
            title: "Unassign all matches",
            message: `Unassign all ${this.plannerAssignedMatchCount} assigned match(es) on this gameday?`,
            confirmLabel: "Unassign all",
            tone: "danger",
        });
    }

    async unassignAllMatches() {
        if (!this.state.currentGamedayId || !this.plannerAssignedMatchCount || this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "unassign_all_matches",
                [this.state.currentGamedayId, this.currentPlannerRevision]
            );
            if (!result.ok) {
                this.state.pendingValidation = {
                    action: "unassign_all",
                    allowForce: false,
                    title: "Unassign all review",
                    validation: result.validation,
                };
                this.notify("Unassign all could not be completed.", "warning");
                return;
            }
            this.clearPlannerSelection();
            this.state.pendingValidation = null;
            await this.loadWorkspace({
                competitionId: this.state.currentCompetitionId,
                divisionId: this.state.currentDivisionId,
                gamedayId: this.state.currentGamedayId,
                includePlannerReferenceData: false,
                unscheduledLimit: this.state.plannerUnscheduledLimit,
            });
            this.notify(`${result.operation_count || 0} match(es) unassigned.`, "success");
        } catch (error) {
            this.notify(error.message || "Unassign all failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async autoScheduleGameday() {
        if (!this.state.currentGamedayId) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "auto_schedule_gameday",
                [
                    this.state.currentGamedayId,
                    this.currentPlannerRevision,
                    false,
                ]
            );
            if (!result.ok) {
                this.state.pendingValidation = {
                    action: "auto_schedule",
                    allowForce: false,
                    title: "Auto-schedule review",
                    validation: result.validation,
                };
                this.notify(
                    result.validation?.blocking?.[0]?.message
                        || "Auto-schedule could not be completed.",
                    "warning"
                );
                return;
            }

            this.clearPlannerSelection();
            this.state.pendingValidation = null;
            await this.loadWorkspace({
                competitionId: this.state.currentCompetitionId,
                divisionId: this.state.currentDivisionId,
                gamedayId: this.state.currentGamedayId,
                includePlannerReferenceData: false,
                unscheduledLimit: this.state.plannerUnscheduledLimit,
            });

            const assignedCount = Number(result.assigned_count || 0);
            const skippedCount = Number((result.skipped || []).length || 0);
            const skippedSummary = (result.skipped_reason_summary || [])
                .map((item) => `${item.code}: ${item.count}`)
                .join(", ");
            this.notify(
                `Auto-schedule assigned ${assignedCount} match(es)`
                + (skippedCount
                    ? `, skipped ${skippedCount}${skippedSummary ? ` (${skippedSummary})` : ""}.`
                    : "."),
                assignedCount ? "success" : "warning"
            );
        } catch (error) {
            this.notify(error.message || "Auto-schedule failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async undoPlannerAction() {
        if (!this.state.currentGamedayId) {
            return;
        }
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "undo_last_planner_operation",
                [this.state.currentGamedayId, this.currentPlannerRevision]
            );
            if (!result.ok) {
                this.state.pendingValidation = {
                    action: "undo",
                    allowForce: false,
                    title: "Undo review",
                    validation: result.validation,
                };
                this.notify("The last planner action could not be undone.", "warning");
                return;
            }
            this.clearPlannerSelection();
            this.state.pendingValidation = null;
            await this.loadWorkspace({
                competitionId: this.state.currentCompetitionId,
                divisionId: this.state.currentDivisionId,
                gamedayId: this.state.currentGamedayId,
                includePlannerReferenceData: false,
                unscheduledLimit: this.state.plannerUnscheduledLimit,
            });
            this.notify("Last planner action undone.", "success");
        } catch (error) {
            this.notify(error.message || "Undo failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async redoPlannerAction() {
        if (!this.state.currentGamedayId) {
            return;
        }
        if (this.state.saving) {
            return;
        }
        this.state.saving = true;
        try {
            const result = await this.orm.call(
                "federation.competition.workspace.service",
                "redo_last_planner_operation",
                [this.state.currentGamedayId, this.currentPlannerRevision]
            );
            if (!result.ok) {
                this.state.pendingValidation = {
                    action: "redo",
                    allowForce: false,
                    title: "Redo review",
                    validation: result.validation,
                };
                this.notify("The last planner action could not be redone.", "warning");
                return;
            }
            this.clearPlannerSelection();
            this.state.pendingValidation = null;
            await this.loadWorkspace({
                competitionId: this.state.currentCompetitionId,
                divisionId: this.state.currentDivisionId,
                gamedayId: this.state.currentGamedayId,
                includePlannerReferenceData: false,
                unscheduledLimit: this.state.plannerUnscheduledLimit,
            });
            this.notify("Last planner action redone.", "success");
        } catch (error) {
            this.notify(error.message || "Redo failed.", "danger");
        } finally {
            this.state.saving = false;
        }
    }

    async forcePendingAssignment() {
        if (!this.state.pendingValidation) {
            return;
        }
        const overrideReason = this.state.overrideReason.pending.trim();
        if (this.state.pendingValidation.action === "bulk_assign") {
            await this.bulkAssignMatches(
                this.state.pendingValidation.matchIds || [],
                true,
                overrideReason
            );
            return;
        }
        await this.assignMatch(
            this.state.pendingValidation.matchId,
            this.state.pendingValidation.slotId,
            true,
            overrideReason
        );
    }

    async assignSelectedToSlot(slotId) {
        if (this.selectedUnscheduledMatches.length !== 1) {
            this.notify(
                "Select exactly one unscheduled match before assigning it to a slot.",
                "warning"
            );
            return;
        }
        await this.assignMatch(this.selectedUnscheduledMatches[0].id, slotId, false);
    }

    openMobileAssign(matchId) {
        this.state.mobileAssign.open = true;
        this.state.mobileAssign.match_id = String(matchId);
        this.state.mobileAssign.gameday_id = String(this.state.currentGamedayId || this.gamedayOptions[0]?.id || "");
        this.state.mobileAssign.slot_id = "";
    }

    closeMobileAssign() {
        this.state.mobileAssign.open = false;
        this.state.mobileAssign.match_id = "";
        this.state.mobileAssign.slot_id = "";
    }

    async confirmMobileAssign() {
        if (!this.state.mobileAssign.match_id || !this.state.mobileAssign.slot_id) {
            return;
        }
        await this.assignMatch(
            Number(this.state.mobileAssign.match_id),
            Number(this.state.mobileAssign.slot_id),
            false
        );
        this.closeMobileAssign();
    }

    clearPendingValidation() {
        this.state.pendingValidation = null;
        this.state.overrideReason.pending = "";
    }
}

registry.category("actions").add(
    "sports_federation_competition_engine.competition_workspace",
    CompetitionWorkspaceAction
);