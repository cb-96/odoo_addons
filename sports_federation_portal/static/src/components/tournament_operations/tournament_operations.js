/** @odoo-module **/

import {
    Component,
    mount,
    onMounted,
    onWillUnmount,
    useState,
    whenReady,
} from "@odoo/owl";

const DIRECT_ACTION_KEYS = new Set(["schedule", "start", "verify", "approve"]);
const COMPACT_LAYOUT_QUERY = "(max-width: 1199.98px)";
const INITIAL_LOAD_TIMEOUT_MS = 30000;

function buttonToneClass(tone, { outline = false, large = false } = {}) {
    const resolvedTone = tone || "primary";
    const classes = ["btn"];
    if (large) {
        classes.push("btn-lg");
    }
    if (outline || resolvedTone === "secondary") {
        classes.push(`btn-outline-${resolvedTone === "dark" ? "secondary" : resolvedTone}`);
    } else if (["warning", "info"].includes(resolvedTone)) {
        classes.push(`btn-${resolvedTone}`, "text-dark");
    } else {
        classes.push(`btn-${resolvedTone}`);
    }
    return classes.join(" ");
}

async function callJsonRpc(url, params = {}, { timeoutMs = 0 } = {}) {
    const controller = timeoutMs && typeof AbortController !== "undefined"
        ? new AbortController()
        : null;
    const timeoutHandle = controller
        ? window.setTimeout(() => controller.abort(), timeoutMs)
        : null;

    try {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                id: Date.now(),
                jsonrpc: "2.0",
                method: "call",
                params,
            }),
            signal: controller?.signal,
        });
        const responseText = await response.text();
        let payload;
        try {
            payload = responseText ? JSON.parse(responseText) : {};
        } catch {
            throw new Error("Your session expired or the server returned an unexpected response.");
        }
        if (payload.error) {
            throw new Error(payload.error.data?.message || payload.error.message || "Unexpected server error.");
        }
        return payload.result;
    } catch (error) {
        if (error?.name === "AbortError") {
            throw new Error("Tournament operations took too long to load. Please try again.");
        }
        throw error;
    } finally {
        if (timeoutHandle) {
            window.clearTimeout(timeoutHandle);
        }
    }
}

class StatusBadge extends Component {
    static template = "sports_federation_portal.TournamentOperationsStatusBadge";

    get badgeClass() {
        const tone = this.props.tone || "secondary";
        if (tone === "warning") {
            return "badge rounded-pill bg-warning text-dark";
        }
        return `badge rounded-pill text-bg-${tone}`;
    }
}

class TournamentSummaryCards extends Component {
    static template = "sports_federation_portal.TournamentOperationsSummaryCards";
    static components = { StatusBadge };

    get cards() {
        const summary = this.props.summary || {};
        return [
            { key: "now_playing", label: "Now playing", count: summary.now_playing_count || 0, tone: "primary" },
            { key: "next_matches", label: "Next matches", count: summary.next_match_count || 0, tone: "info" },
            { key: "missing_results", label: "Missing results", count: summary.missing_result_count || 0, tone: "warning" },
            { key: "needs_validation", label: "Needs validation", count: summary.needs_validation_count || 0, tone: "info" },
            { key: "court_issues", label: "Court issues", count: summary.court_issue_count || 0, tone: "danger" },
            { key: "completed", label: "Completed", count: summary.completed_count || 0, tone: "success" },
        ];
    }

    onSelectCard(ev) {
        this.props.onSelect(ev.currentTarget.dataset.key);
    }
}

class TournamentActionQueue extends Component {
    static template = "sports_federation_portal.TournamentOperationsActionQueue";
    static components = { StatusBadge };

    onOpenMatch(ev) {
        this.props.onOpenMatch(Number(ev.currentTarget.dataset.matchId));
    }
}

class TournamentCourtSummaries extends Component {
    static template = "sports_federation_portal.TournamentOperationsCourtSummaries";
    static components = { StatusBadge };

    onSelectCourt(ev) {
        this.props.onSelectCourt(ev.currentTarget.dataset.courtKey);
    }
}

class TournamentFilters extends Component {
    static template = "sports_federation_portal.TournamentOperationsFilters";

    onSearchInput(ev) {
        this.props.onSearchInput(ev.target.value);
    }

    onFilterChange(ev) {
        this.props.onFilterChange(ev.target.name, ev.target.value);
    }

    onToggleFlag(ev) {
        this.props.onToggleFlag(ev.currentTarget.dataset.flag);
    }

    onClearFilters() {
        this.props.onClear();
    }
}

class MatchCard extends Component {
    static template = "sports_federation_portal.TournamentOperationsMatchCard";
    static components = { StatusBadge };

    onSelectMatch(ev) {
        if (ev) {
            ev.stopPropagation();
        }
        this.props.onSelect(this.props.match.id);
    }

    onPrimaryAction(ev) {
        ev.stopPropagation();
        this.props.onPrimaryAction(this.props.match);
    }

    get scoreLabel() {
        const match = this.props.match;
        if (!match.has_score) {
            return "Result pending";
        }
        return `${match.home_score} - ${match.away_score}`;
    }

    get visibleAttentionItems() {
        return (this.props.match.attention_items || []).slice(0, 2);
    }

    get selectedClass() {
        return this.props.selected ? "border-primary shadow-sm" : "";
    }

    get primaryActionClass() {
        return buttonToneClass(this.props.match.primary_action?.tone || "primary");
    }
}

class CourtMatchGroup extends Component {
    static template = "sports_federation_portal.TournamentOperationsCourtMatchGroup";
    static components = { MatchCard, StatusBadge };
}

class ResultEntryPanel extends Component {
    static template = "sports_federation_portal.TournamentOperationsResultEntryPanel";
    static components = { StatusBadge };

    onClosePanel() {
        this.props.onClose();
    }

    onFieldInput(ev) {
        this.props.onFieldInput(ev.target.name, ev.target.value);
    }

    onActionClick(ev) {
        this.props.onAction(ev.currentTarget.dataset.action);
    }

    onPreviousTask() {
        this.props.onPreviousTask();
    }

    onNextTask() {
        this.props.onNextTask();
    }

    get actionKeys() {
        const match = this.props.match;
        if (!match) {
            return [];
        }
        return [
            match.primary_action?.key,
            ...(match.secondary_actions || []).map((action) => action.key),
        ].filter(Boolean);
    }

    get scoreInputsDisabled() {
        const match = this.props.match;
        return !match.capabilities.can_edit_scores || match.result_state === "approved";
    }

    get primaryActionClass() {
        return buttonToneClass(this.props.match.primary_action?.tone || "primary", { large: true });
    }

    secondaryActionClass(action) {
        return buttonToneClass(action.tone || "secondary", { outline: true });
    }
}

export class TournamentOperationsApp extends Component {
    static template = "sports_federation_portal.TournamentOperationsApp";
    static components = {
        CourtMatchGroup,
        ResultEntryPanel,
        StatusBadge,
        TournamentActionQueue,
        TournamentCourtSummaries,
        TournamentFilters,
        TournamentSummaryCards,
    };

    setup() {
        this.state = useState({
            bannerError: null,
            data: null,
            fatalError: null,
            fatalErrorType: null,
            filters: {
                summaryKey: "all",
                search: "",
                court: "all",
                matchState: "all",
                resultState: "all",
                timeline: "all",
                referee: "all",
                attentionOnly: false,
                missingOnly: false,
                validationIssuesOnly: false,
            },
            form: this._emptyForm(),
            formDirty: false,
            loading: true,
            offline: !navigator.onLine,
            compactLayout: typeof window !== "undefined" && window.matchMedia(COMPACT_LAYOUT_QUERY).matches,
            refreshing: false,
            savingAction: null,
            selectedMatchId: null,
            successMessage: null,
            panelError: null,
        });
        this.pollHandle = null;
        this.handleOnline = () => {
            this.state.offline = false;
            this.state.bannerError = null;
            if (this.state.data) {
                this.loadPayload({ silent: true, resetForm: false });
            }
        };
        this.handleOffline = () => {
            this.state.offline = true;
            this.state.bannerError = "You are offline. You can review the board, but changes cannot be saved until your connection returns.";
        };
        this.handleResize = () => {
            this.state.compactLayout = window.matchMedia(COMPACT_LAYOUT_QUERY).matches;
        };
        this.handleKeydown = (event) => {
            const lowerKey = event.key?.toLowerCase?.() || event.key;
            const tagName = event.target?.tagName?.toLowerCase?.() || "";
            const isTypingTarget = ["input", "textarea", "select"].includes(tagName) || event.target?.isContentEditable;

            if ((event.metaKey || event.ctrlKey) && lowerKey === "s" && this.selectedMatch && !this.state.savingAction) {
                const actionKey = this.selectedMatch.primary_action?.key;
                if (actionKey && actionKey !== "view") {
                    event.preventDefault();
                    this.runAction(actionKey);
                }
                return;
            }
            if (event.key === "Escape" && this.selectedMatch && this.state.compactLayout) {
                event.preventDefault();
                this.closePanel();
                return;
            }
            if (isTypingTarget) {
                return;
            }
            if (event.altKey && event.key === "ArrowDown") {
                event.preventDefault();
                this.selectAdjacentTask(1);
            }
            if (event.altKey && event.key === "ArrowUp") {
                event.preventDefault();
                this.selectAdjacentTask(-1);
            }
        };
        onMounted(() => {
            window.addEventListener("online", this.handleOnline);
            window.addEventListener("offline", this.handleOffline);
            window.addEventListener("resize", this.handleResize);
            window.addEventListener("keydown", this.handleKeydown);
            this.loadPayload();
            this.startPolling();
        });
        onWillUnmount(() => {
            window.removeEventListener("online", this.handleOnline);
            window.removeEventListener("offline", this.handleOffline);
            window.removeEventListener("resize", this.handleResize);
            window.removeEventListener("keydown", this.handleKeydown);
            if (this.pollHandle) {
                window.clearInterval(this.pollHandle);
            }
        });
    }

    _emptyForm() {
        return {
            home_score: "",
            away_score: "",
            result_contest_reason: "",
            result_correction_reason: "",
        };
    }

    _buildFormFromMatch(match) {
        return {
            home_score: match.has_score ? String(match.home_score) : "",
            away_score: match.has_score ? String(match.away_score) : "",
            result_contest_reason: match.result_contest_reason || "",
            result_correction_reason: match.result_correction_reason || "",
        };
    }

    get pollIntervalMs() {
        return Number(this.props.pollIntervalMs) || 60000;
    }

    get selectedMatch() {
        if (!this.state.data || !this.state.selectedMatchId) {
            return null;
        }
        return this.state.data.matches.find((match) => match.id === this.state.selectedMatchId) || null;
    }

    get actionQueue() {
        return this.state.data?.action_queue || [];
    }

    get courtSummaries() {
        return this.state.data?.court_summaries || [];
    }

    get actionableMatchIds() {
        const queueIds = this.actionQueue.map((item) => item.match_id);
        if (queueIds.length) {
            return queueIds;
        }
        return this.filteredMatches
            .filter((match) => match.needs_attention || match.primary_action?.key !== "view")
            .map((match) => match.id);
    }

    get selectedTaskPosition() {
        if (!this.selectedMatch) {
            return 0;
        }
        const index = this.actionableMatchIds.indexOf(this.selectedMatch.id);
        return index === -1 ? 0 : index + 1;
    }

    get filteredMatches() {
        if (!this.state.data) {
            return [];
        }
        const filters = this.state.filters;
        const search = filters.search.trim().toLowerCase();
        return this.state.data.matches.filter((match) => {
            if (filters.summaryKey !== "all") {
                const summaryChecks = {
                    now_playing: match.is_now_playing,
                    next_matches: ["upcoming", "overdue"].includes(match.timeline_bucket),
                    missing_results: match.is_missing_result,
                    needs_validation: match.needs_validation,
                    court_issues: match.has_court_issue,
                    completed: match.is_completed,
                };
                if (!summaryChecks[filters.summaryKey]) {
                    return false;
                }
            }
            if (search) {
                const haystack = [
                    match.name,
                    match.home_team_name,
                    match.away_team_name,
                    match.court_name,
                    match.venue_name,
                    match.referee_summary,
                ]
                    .filter(Boolean)
                    .join(" ")
                    .toLowerCase();
                if (!haystack.includes(search)) {
                    return false;
                }
            }
            if (filters.court !== "all" && String(match.court_id || "unassigned") !== filters.court) {
                return false;
            }
            if (filters.matchState !== "all" && match.state !== filters.matchState) {
                return false;
            }
            if (filters.resultState !== "all" && match.result_state !== filters.resultState) {
                return false;
            }
            if (filters.timeline !== "all") {
                if (filters.timeline === "upcoming" && !["upcoming", "overdue"].includes(match.timeline_bucket)) {
                    return false;
                }
                if (filters.timeline === "current" && match.timeline_bucket !== "current") {
                    return false;
                }
                if (filters.timeline === "completed" && match.timeline_bucket !== "completed") {
                    return false;
                }
            }
            if (filters.referee !== "all" && match.referee_name !== filters.referee) {
                return false;
            }
            if (filters.attentionOnly && !match.needs_attention) {
                return false;
            }
            if (filters.missingOnly && !match.is_missing_result) {
                return false;
            }
            if (filters.validationIssuesOnly && !match.has_validation_issue) {
                return false;
            }
            return true;
        });
    }

    get groupedMatches() {
        const groups = new Map();
        const summaryByCourt = new Map(
            (this.state.data?.court_summaries || []).map((summary) => [summary.court_key, summary])
        );
        for (const match of this.filteredMatches) {
            const key = String(match.court_id || "unassigned");
            if (!groups.has(key)) {
                groups.set(key, {
                    key,
                    name: match.court_name,
                    venueName: match.venue_name,
                    matches: [],
                });
            }
            groups.get(key).matches.push(match);
        }
        return [...groups.values()]
            .map((group) => ({
                ...group,
                courtSummary: summaryByCourt.get(group.key) || null,
                liveCount: group.matches.filter((match) => match.is_now_playing).length,
                issueCount: group.matches.filter((match) => match.needs_attention).length,
                nextMatch: group.matches.find((match) => ["upcoming", "overdue"].includes(match.timeline_bucket)) || null,
                matches: group.matches.sort((left, right) => this.compareMatches(left, right)),
            }))
            .sort((left, right) => {
                const leftWeight = this.getGroupWeight(left);
                const rightWeight = this.getGroupWeight(right);
                if (leftWeight !== rightWeight) {
                    return leftWeight - rightWeight;
                }
                return left.name.localeCompare(right.name);
            });
    }

    get hasActiveFilters() {
        const filters = this.state.filters;
        return (
            filters.summaryKey !== "all"
            || filters.search
            || filters.court !== "all"
            || filters.matchState !== "all"
            || filters.resultState !== "all"
            || filters.timeline !== "all"
            || filters.referee !== "all"
            || filters.attentionOnly
            || filters.missingOnly
            || filters.validationIssuesOnly
        );
    }

    getGroupWeight(group) {
        if (group.liveCount) {
            return 0;
        }
        if (group.issueCount) {
            return 1;
        }
        if (group.nextMatch) {
            return 2;
        }
        return 3;
    }

    compareMatches(left, right) {
        const bucketWeight = {
            current: 0,
            overdue: 1,
            upcoming: 2,
            completed: 3,
        };
        const leftWeight = bucketWeight[left.timeline_bucket] ?? 10;
        const rightWeight = bucketWeight[right.timeline_bucket] ?? 10;
        if (leftWeight !== rightWeight) {
            return leftWeight - rightWeight;
        }
        return (left.scheduled_datetime || "").localeCompare(right.scheduled_datetime || "");
    }

    async loadPayload({ silent = false, resetForm = false } = {}) {
        if (!silent) {
            this.state.loading = true;
            this.state.fatalError = null;
            this.state.fatalErrorType = null;
        } else {
            this.state.refreshing = true;
        }
        try {
            const result = await callJsonRpc(this.props.loadUrl, {}, {
                timeoutMs: INITIAL_LOAD_TIMEOUT_MS,
            });
            if (!result?.ok) {
                this.handleStructuredError(result?.error, { fatal: !this.state.data });
                return;
            }
            this.applyPayload(result.payload, { resetForm });
            this.state.bannerError = null;
            this.state.fatalError = null;
            this.state.fatalErrorType = null;
        } catch (error) {
            const message = !navigator.onLine
                ? "You are offline. You can review the board, but changes cannot be saved until your connection returns."
                : (error.message || "We could not load the tournament operations board.");
            if (this.state.data) {
                this.state.bannerError = message;
            } else {
                this.state.fatalError = message;
                this.state.fatalErrorType = "error";
            }
        } finally {
            this.state.loading = false;
            this.state.refreshing = false;
        }
    }

    applyPayload(payload, { resetForm = false } = {}) {
        const previousMatchId = this.state.selectedMatchId;
        const shouldPreserveSelection = previousMatchId
            && payload.matches.some((match) => match.id === previousMatchId);
        this.state.data = payload;
        if (shouldPreserveSelection) {
            this.state.selectedMatchId = previousMatchId;
            if (resetForm || !this.state.formDirty) {
                this.state.form = this._buildFormFromMatch(this.selectedMatch);
                this.state.formDirty = false;
            }
            return;
        }
        const defaultMatchId = payload.default_match_id || null;
        if (defaultMatchId && !this.state.compactLayout) {
            this.selectMatch(defaultMatchId, { preserveMessages: true });
            return;
        }
        this.state.selectedMatchId = null;
        this.state.form = this._emptyForm();
        this.state.formDirty = false;
    }

    handleStructuredError(error, { fatal = false } = {}) {
        const message = error?.message || "We could not complete that action. Please try again.";
        if (fatal) {
            this.state.fatalError = message;
            this.state.fatalErrorType = error?.type || "error";
            return;
        }
        if (error?.type === "validation") {
            this.state.panelError = message;
            return;
        }
        this.state.bannerError = message;
    }

    selectSummaryCard(key) {
        this.state.filters.summaryKey = this.state.filters.summaryKey === key ? "all" : key;
    }

    updateSearch(value) {
        this.state.filters.search = value;
    }

    updateFilter(name, value) {
        this.state.filters[name] = value;
    }

    toggleFlag(flag) {
        this.state.filters[flag] = !this.state.filters[flag];
    }

    clearFilters() {
        this.state.filters.summaryKey = "all";
        this.state.filters.search = "";
        this.state.filters.court = "all";
        this.state.filters.matchState = "all";
        this.state.filters.resultState = "all";
        this.state.filters.timeline = "all";
        this.state.filters.referee = "all";
        this.state.filters.attentionOnly = false;
        this.state.filters.missingOnly = false;
        this.state.filters.validationIssuesOnly = false;
    }

    selectCourtSummary(courtKey) {
        this.state.filters.court = this.state.filters.court === courtKey ? "all" : courtKey;
    }

    focusPrimaryField() {
        window.requestAnimationFrame(() => {
            const scoreField = document.getElementById("sf_ops_home_score");
            if (scoreField && !scoreField.disabled) {
                scoreField.focus();
                if (scoreField.select) {
                    scoreField.select();
                }
            }
        });
    }

    selectAdjacentTask(direction) {
        const ids = this.actionableMatchIds;
        if (!ids.length) {
            return;
        }
        let index = ids.indexOf(this.state.selectedMatchId);
        if (index === -1) {
            index = direction > 0 ? -1 : 0;
        }
        const nextIndex = (index + direction + ids.length) % ids.length;
        this.selectMatch(ids[nextIndex], { preserveMessages: true, focusPanel: true });
    }

    selectMatch(matchId, { preserveMessages = false, focusPanel = false } = {}) {
        if (this.state.selectedMatchId === matchId) {
            this.state.selectedMatchId = null;
            this.state.form = this._emptyForm();
            this.state.formDirty = false;
            this.state.panelError = null;
            if (!preserveMessages) {
                this.state.successMessage = null;
            }
            return;
        }
        this.state.selectedMatchId = matchId;
        this.state.panelError = null;
        if (!preserveMessages) {
            this.state.successMessage = null;
        }
        if (this.selectedMatch) {
            this.state.form = this._buildFormFromMatch(this.selectedMatch);
            this.state.formDirty = false;
            if (focusPanel || this.state.compactLayout) {
                this.focusPrimaryField();
            }
        }
    }

    closePanel() {
        this.state.selectedMatchId = null;
        this.state.form = this._emptyForm();
        this.state.formDirty = false;
        this.state.panelError = null;
        this.state.successMessage = null;
    }

    updateFormField(name, value) {
        this.state.form[name] = value;
        this.state.formDirty = true;
        this.state.panelError = null;
        this.state.successMessage = null;
    }

    async handlePrimaryAction(match) {
        const actionKey = match.primary_action?.key || "view";
        if (this.state.selectedMatchId !== match.id) {
            this.selectMatch(match.id, { preserveMessages: true });
        }
        if (DIRECT_ACTION_KEYS.has(actionKey)) {
            await this.runAction(actionKey);
        }
    }

    buildActionUrl(matchId) {
        return this.props.actionUrlTemplate.replace("__MATCH_ID__", String(matchId));
    }

    async runAction(actionKey) {
        const match = this.selectedMatch;
        if (!match) {
            return;
        }
        this.state.savingAction = actionKey;
        this.state.panelError = null;
        this.state.successMessage = null;
        try {
            const result = await callJsonRpc(this.buildActionUrl(match.id), {
                action: actionKey,
                home_score: this.state.form.home_score,
                away_score: this.state.form.away_score,
                result_contest_reason: this.state.form.result_contest_reason,
                result_correction_reason: this.state.form.result_correction_reason,
            });
            if (!result?.ok) {
                this.handleStructuredError(result?.error);
                return;
            }
            this.applyPayload(result.payload, { resetForm: true });
            const followUp = actionKey === "save_score" && this.selectedMatch?.next_step?.label
                ? ` Next step: ${this.selectedMatch.next_step.label}.`
                : "";
            this.state.successMessage = `${result.message || "Update saved."}${followUp}`;
            this.state.bannerError = null;
            this.state.formDirty = false;
            if (this.selectedMatch && this.state.compactLayout) {
                this.focusPrimaryField();
            }
        } catch (error) {
            this.state.panelError = !navigator.onLine
                ? "Your connection was lost before the change was saved. Reconnect and submit again."
                : (error.message || "We could not complete that action. Please try again.");
        } finally {
            this.state.savingAction = null;
        }
    }

    openQueueMatch(matchId) {
        this.selectMatch(matchId, { preserveMessages: true, focusPanel: true });
    }

    async refreshBoard() {
        await this.loadPayload({ silent: true, resetForm: !this.state.formDirty });
    }

    startPolling() {
        if (this.pollHandle) {
            window.clearInterval(this.pollHandle);
        }
        this.pollHandle = window.setInterval(() => {
            if (document.hidden || this.state.savingAction || this.state.formDirty) {
                return;
            }
            this.loadPayload({ silent: true, resetForm: false });
        }, this.pollIntervalMs);
    }
}

function mountTournamentOperationsApp() {
    const target = document.getElementById("sf_tournament_operations_root");
    if (!target) {
        return;
    }
    mount(TournamentOperationsApp, target, {
        props: {
            tournamentId: Number(target.dataset.tournamentId),
            loadUrl: target.dataset.loadUrl,
            actionUrlTemplate: target.dataset.actionUrlTemplate,
            pollIntervalMs: Number(target.dataset.pollIntervalMs || 60000),
        },
    });
}

whenReady(() => {
    mountTournamentOperationsApp();
});
