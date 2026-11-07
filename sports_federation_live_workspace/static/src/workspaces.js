/** @odoo-module **/
import { restoreCourtCache } from "./court_cache";
import { copy, readJournal, durableWrite, acknowledgedState, saveState, nextMatch, pruneCleanJournals } from "./mobile_recovery";
import { destinationLabel, canApply, comparable, navigationTarget, formatEventTime } from "./visual_helpers";
import { Component, useEffect, useRef, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { _t } from "@web/core/l10n/translation";

const clone = (value) => JSON.parse(JSON.stringify(value));
const key = () => crypto.randomUUID();

export class CourtWorkspace extends Component {
    static template = "sports_federation_live_workspace.Court";
    static props = ["*"];
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ courts: [], selected: "", board: null, match: null, draft: null,
            pending: [], busy: false, dirty: false, error: "", conflict: false, storageFailed: false,
            offline: !navigator.onLine, contextUnchecked: false, recoveryNotice: "", journalBlocked: false,
            queueOpen: false, courtLoading: false });
        this.storagePrefix = `sf-court:v1:${session.db}:${session.uid}:`;
        this.expectedRaw = null;
        this.releaseLease = null;
        this.online = () => { this.state.offline = false; if (this.state.pending.length) this.sync(); else this.refreshStatus(); };
        this.offline = () => { this.state.offline = true; this.state.contextUnchecked = true; };
        this.unload = event => { if (this.state.dirty || this.state.pending.length || this.state.storageFailed) {
            event.preventDefault(); event.returnValue = "";
        }};
        this.storageChanged = event => {
            if (this.state.match && event.key === this.storageKey && event.newValue !== this.expectedRaw) {
                this.state.conflict = true;
                this.state.journalBlocked = true;
                this.state.error = _t("Another tab changed this journal. Export this screen's evidence before reloading.");
            }
        };
        window.addEventListener("online", this.online);
        window.addEventListener("offline", this.offline);
        window.addEventListener("beforeunload", this.unload);
        window.addEventListener("storage", this.storageChanged);
        onWillUnmount(() => {
            this.releaseLease?.();
            window.removeEventListener("online", this.online);
            window.removeEventListener("offline", this.offline);
            window.removeEventListener("beforeunload", this.unload);
            window.removeEventListener("storage", this.storageChanged);
        });
        onWillStart(async () => {
            // Synchronised journals only repeat server state; unreadable or unsent ones stay.
            try { pruneCleanJournals(localStorage, this.storagePrefix); } catch { /* Storage unavailable: nothing to prune. */ }
            try {
                this.state.courts = await this.orm.call("federation.court.commands", "courts", []);
                let remembered;
                try { remembered = JSON.parse(localStorage.getItem(`${this.storagePrefix}last`) || 'null'); } catch { /* No trusted context. */ }
                const params = this.props.action?.params || {};
                const index = this.state.courts.findIndex(court => court.matchday_id === Number(params.matchday_id || remembered?.matchday_id)
                    && court.court_id === Number(params.court_id || remembered?.court_id));
                if (index >= 0 || this.state.courts.length === 1) {
                    await this.chooseCourt({target: {value: String(index >= 0 ? index : 0)}}, Number(params.match_id || remembered?.match_id) || null);
                }
            } catch (error) { this.state.error = this.message(error); }
        });
    }
    focusError() { setTimeout(() => document.getElementById("court-error")?.focus(), 0); }
    message(error) { return error?.data?.message || error?.message || _t("Operation failed. Local evidence retained."); }
    eventTime(value) { return formatEventTime(value, this.state.board?.timezone || "UTC"); }
    get access() { return this.state.courts[Number(this.state.selected)]; }
    get storageKey() { return `${this.storagePrefix}${this.access.matchday_id}:${this.access.court_id}:${this.state.match.match_id}`; }
    get statusCode() { return saveState(this.state); }
    get status() {
        return {memory: _t("Not saved. Keep this screen open."), device: _t("Saved on this device. Not submitted."),
            submission_pending: _t("Submission queued on this device. Not confirmed by server."),
            synchronised: _t("Saved to server. Not submitted."), submitted: _t("Submitted. Awaiting review."),
            verified: _t("Reviewed. Awaiting approval."), approved: _t("Approved official result"),
            contested: _t("Disputed. Correction required."), unchecked: _t("No match loaded")}[this.statusCode];
    }
    get locked() {
        return this.state.match && (this.state.match.submitted || this.state.match.closed
            || !["draft", "corrected"].includes(this.state.match.result_state)
            || this.state.pending.some(command => command.operation === 'submit'));
    }
    async lease(name) {
        this.releaseLease?.(); this.releaseLease = null;
        if (!navigator.locks) throw new Error(_t("Court editing requires a secure browser with Web Locks. Use a supported browser or the supervised fallback."));
        return new Promise(resolve => {
            navigator.locks.request(name, {ifAvailable: true}, async lock => {
                if (!lock) { resolve(false); return; }
                await new Promise(release => { this.releaseLease = release; resolve(true); });
            }).catch(() => resolve(false));
        });
    }
    async chooseCourt(event, preferredMatch = null) {
        const selected = event.target.value;
        if (this.state.courtLoading || (this.state.selected === selected && this.state.board)) return;
        if (this.state.pending.length || this.state.dirty || this.state.storageFailed) {
            this.state.error = _t("Synchronise or export this match before changing courts."); return;
        }
        this.releaseLease?.(); this.releaseLease = null;
        this.state.selected = selected;
        this.state.match = null; this.state.board = null;
        if (this.state.selected === "") return;
        this.state.courtLoading = true;
        try {
            this.state.board = await this.orm.call("federation.court.commands", "load", [this.access.matchday_id, this.access.court_id]);
            const match = this.state.board.queue.find(item => item.id === preferredMatch) || nextMatch(this.state.board.queue);
            if (preferredMatch) await this.openMatch(preferredMatch);
            else if (match) await this.openMatch(match.id);
        } catch (error) { this.state.error = this.message(error); }
        finally { this.state.courtLoading = false; }
    }
    async openMatch(id) {
        if (this.state.pending.length || this.state.dirty || this.state.storageFailed) {
            this.state.error = _t("Synchronise or export this match first."); return;
        }
        this.state.busy = true;
        this.state.match = null; this.state.draft = null;
        const name = `${this.storagePrefix}${this.access.matchday_id}:${this.access.court_id}:${id}`;
        let cached = null;
        this.state.journalBlocked = false;
        try {
            if (!await this.lease(name)) { this.state.journalBlocked = true; this.state.conflict = true; throw new Error(_t("This match is already open in another tab. Close that tab before editing.")); }
            try { this.expectedRaw = localStorage.getItem(name); cached = readJournal(this.expectedRaw); }
            catch (error) { this.state.journalBlocked = true; this.state.conflict = true; throw error; }
            let result;
            try {
                result = await this.orm.call("federation.court.commands", "open_match", [this.access.matchday_id, this.access.court_id, id]);
                this.state.contextUnchecked = false;
            } catch (error) {
                // Never fall back after an access/validation response. Offline cache is not authorisation.
                if (error?.data || !cached?.snapshot || cached.snapshot.match_id !== id) throw error;
                result = cached.snapshot;
                this.state.contextUnchecked = true;
                this.state.recoveryNotice = _t("Recovered previously loaded evidence. Current access and match context are not verified; reconnect before official submission.");
            }
            Object.assign(this.state, restoreCourtCache(result, cached));
            this.state.storageFailed = false;
            this.state.error = this.state.conflict ? _t("Match context changed. Keep local evidence and reconcile explicitly.") : "";
            if (!cached || !(cached.dirty || cached.pending.length)) this.persist();
            if (this.state.pending.length && navigator.onLine && !this.state.conflict) {
                this.state.recoveryNotice = _t("Pending commands recovered with their original keys. Synchronise to confirm the server outcome.");
            }
        } catch (error) { this.state.error = this.message(error); }
        finally { this.state.busy = false; }
    }
    persist() {
        if (!this.state.match || this.state.journalBlocked) return false;
        const snapshot = copy(this.state.match);
        delete snapshot.lineups; // Player lists are not needed for score recovery.
        const record = {schema: 2, draft: copy(this.state.draft), pending: copy(this.state.pending),
            dirty: this.state.dirty, saved_at: new Date().toISOString(), snapshot,
            base: {revision: this.state.match.revision, signature: this.state.match.signature}};
        try {
            this.expectedRaw = durableWrite(localStorage, this.storageKey, record, this.expectedRaw);
            this.state.storageFailed = false;
            try { localStorage.setItem(`${this.storagePrefix}last`, JSON.stringify({matchday_id: this.access.matchday_id, court_id: this.access.court_id, match_id: this.state.match.match_id})); } catch { /* Score journal already verified. */ }
            return true;
        } catch (error) {
            this.state.storageFailed = true;
            this.state.error = this.message(error);
            return false;
        }
    }
    edited() { this.state.dirty = true; this.persist(); }
    score(side, amount) {
        if (this.locked || this.state.busy || this.state.conflict) return;
        this.state.draft[side] = Math.max(0, this.state.draft[side] + amount); this.edited();
    }
    onHomeScore(event) { this.state.draft.home = Number(event.target.value); this.edited(); }
    onAwayScore(event) { this.state.draft.away = Number(event.target.value); this.edited(); }
    addPeriod() { this.state.draft.periods.push({home: 0, away: 0}); this.retotal(); }
    removePeriod(index) { this.state.draft.periods.splice(index, 1); this.retotal(); }
    periodScore(index, side, event) { this.state.draft.periods[index][side] = Number(event.target.value); this.retotal(); }
    retotal() {
        // Sets mode: the match score is the sum of set points (won / drawn).
        const [win, draw] = this.state.match.set_points || [1, 0];
        const points = (own, other) => own > other ? win : own === other ? draw : 0;
        const sets = this.state.match.mode === "sets";
        this.state.draft.home = this.state.draft.periods.reduce((sum, period) => sum + (sets ? points(period.home, period.away) : period.home), 0);
        this.state.draft.away = this.state.draft.periods.reduce((sum, period) => sum + (sets ? points(period.away, period.home) : period.away), 0);
        this.edited();
    }
    async command(operation) {
        if (this.locked || this.state.busy || this.state.conflict || this.state.journalBlocked) return;
        if (operation === "submit" && !window.confirm(_t("Submit these scores for independent review? They become read-only after server confirmation."))) return;
        if (operation === "undo" && this.state.pending.length) { this.state.error = _t("Synchronise pending commands before server undo."); return; }
        if (this.state.pending.length >= 100) { this.state.error = _t("Synchronise or export this journal before adding commands."); return; }
        const command = {key: key(), revision: this.state.match.revision + this.state.pending.length,
            operation, payload: copy(this.state.draft), signature: this.state.match.signature};
        this.state.pending.push(command); this.state.dirty = false;
        if (!this.persist()) return; // No acknowledged device save and no send after a failed durable write.
        if (navigator.onLine) await this.sync();
    }
    async sync() {
        if (!this.state.match || !this.state.pending.length || this.state.busy || this.state.conflict || this.state.journalBlocked) return;
        if (!this.persist()) return;
        this.state.busy = true;
        const commands = copy(this.state.pending);
        const unsentDraft = this.state.dirty ? copy(this.state.draft) : null;
        const originalSignature = this.state.match.signature;
        try {
            const result = await this.orm.call("federation.court.commands", "sync", [this.access.matchday_id,
                this.access.court_id, this.state.match.match_id, commands]);
            const confirmed = acknowledgedState(result.current, commands, result.acknowledged_keys);
            this.state.match = {...this.state.match, ...confirmed.match};
            this.state.pending = confirmed.pending; this.state.draft = unsentDraft || confirmed.draft; this.state.dirty = Boolean(unsentDraft);
            this.state.contextUnchecked = false; this.state.recoveryNotice = ""; this.state.error = "";
            if (unsentDraft && (result.current.signature !== originalSignature || result.current.revision !== commands.at(-1).revision + 1)) {
                this.state.conflict = true; this.state.error = _t("Queued commands were acknowledged, but later edits need explicit reconciliation with changed context.");
            }
            this.persist();
        } catch (error) {
            this.state.error = this.message(error);
            this.state.contextUnchecked = true;
            if (error?.data) this.state.conflict = true;
            this.focusError();
        } finally { this.state.busy = false; }
        // A board-refresh failure must not undo a confirmed receipt or label it unsaved.
        if (!this.state.pending.length) {
            try { this.state.board = await this.orm.call("federation.court.commands", "load", [this.access.matchday_id, this.access.court_id]); }
            catch { this.state.recoveryNotice = _t("Result acknowledgement is confirmed; the match queue could not refresh."); }
        }
    }
    async refreshStatus() {
        if (!this.state.match || this.state.busy) return;
        if (this.state.pending.length) return this.sync();
        this.state.busy = true;
        try {
            const result = await this.orm.call("federation.court.commands", "inspect", [this.access.matchday_id, this.access.court_id, this.state.match.match_id]);
            if (this.state.dirty && (result.revision !== this.state.match.revision || result.signature !== this.state.match.signature)) {
                this.state.conflict = true;
                this.state.error = _t("Another session changed the match. Local edits are retained; reconcile explicitly.");
            } else if (!this.state.dirty) {
                this.state.match = {...this.state.match, ...result}; this.state.draft = copy(result.payload); this.persist();
            }
            this.state.contextUnchecked = false;
        } catch (error) { this.state.error = this.message(error); this.state.contextUnchecked = true; }
        finally { this.state.busy = false; }
    }
    exportEvidence() {
        const match = this.state.match ? copy(this.state.match) : null;
        if (match) delete match.lineups;
        const value = {schema: 2, court: this.access, match, draft: this.state.draft,
            pending: this.state.pending, original_journal: this.expectedRaw, exported_at: new Date().toISOString()};
        const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: "application/json"}));
        const anchor = document.createElement("a"); anchor.href = url; anchor.download = `court-${this.state.match?.match_id || 'recovery'}-evidence.json`;
        anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    async reconcile() {
        if (!this.state.match || this.state.busy) return;
        this.exportEvidence();
        if (!window.confirm(_t("After retaining the exported evidence, reload the server draft? Local scores will not be merged."))) return;
        this.state.busy = true;
        try {
            const result = await this.orm.call("federation.court.commands", "inspect", [this.access.matchday_id, this.access.court_id, this.state.match.match_id]);
            // Do not destroy the old journal before the authoritative read succeeds.
            this.expectedRaw = localStorage.getItem(this.storageKey);
            this.state.match = {...this.state.match, ...result}; this.state.draft = copy(result.payload);
            this.state.pending = []; this.state.dirty = false; this.state.journalBlocked = false;
            this.state.conflict = result.signature !== result.draft_signature;
            this.state.contextUnchecked = false; this.persist();
        } catch (error) { this.state.error = this.message(error); }
        finally { this.state.busy = false; }
    }
    async acknowledge() {
        if (this.state.pending.length || this.state.dirty || this.locked || this.state.busy || this.state.journalBlocked) return;
        const reason = window.prompt(_t("Explain why the current server draft is valid in the changed match context."));
        if (!reason) return;
        this.state.busy = true;
        try {
            const result = await this.orm.call("federation.court.commands", "reconcile", [this.access.matchday_id,
                this.access.court_id, this.state.match.match_id, this.state.match.revision, reason]);
            this.state.match = {...this.state.match, ...result}; this.state.draft = copy(result.payload);
            this.state.conflict = false; this.state.dirty = false; this.state.contextUnchecked = false; this.persist();
        } catch (error) { this.state.error = this.message(error); }
        finally { this.state.busy = false; }
    }
    async openResultReview() {
        if (!this.state.match || this.state.pending.length || this.state.dirty) return;
        await this.action.doAction({type: "ir.actions.act_window", res_model: "federation.match",
            res_id: this.state.match.match_id, views: [[false, "form"]], target: "current"});
    }
    async nextMatch() {
        const queue = this.state.board?.queue || [];
        const current = queue.findIndex(match => match.id === this.state.match?.match_id);
        const next = queue.slice(current + 1).find(match => ["draft", "corrected"].includes(match.result_state));
        if (next) await this.openMatch(next.id);
    }
}

export class VisualPlan extends Component {
    static template = "sports_federation_live_workspace.Plan";
    static props = ["*"];
    setup() {
        this.root = useRef("visualRoot");
        this.orm = useService("orm"); this.action = useService("action");
        this.id = this.props.action.params?.schedule_id || this.props.action.context?.active_id;
        this.state = useState({ data: null, stale: false, preview: null, fixture: "", reason: "", error: "", busy: false,
            destinations: null, selectedSlot: null, candidateA: null, comparison: null, announcement: "",
            constraint: { name: "", kind: "team_window", team_id: "", court_id: "", start: "", end: "", minutes: 0 } });
        onWillStart(() => this.refresh());
        useEffect(() => {
            if (this.state.preview) this.root.el?.querySelector('[data-preview-heading]')?.focus();
        }, () => [this.state.preview?.id]);
    }
    async run(callback, allowStale = false) {
        if (this.state.busy || (this.state.stale && !allowStale)) return;
        this.state.busy = true; this.state.error = "";
        try { return await callback(); } catch (error) { this.state.error = error?.data?.message || error.message; }
        finally { this.state.busy = false; }
    }
    async refresh() { await this.run(async () => {
        try {
            this.state.data = await this.orm.call("federation.visual.planning", "load", [this.id]);
            this.state.stale = false;
            this.state.preview = null; this.state.destinations = null; this.state.candidateA = null; this.state.comparison = null;
        } catch (error) {
            this.state.stale = true;
            throw error;
        }
    }, true); }
    get courts() { return [...new Map(this.state.data.slots.map(s => [s.court_id, { id: s.court_id, name: s.court_name }])).values()]; }
    get times() { return [...new Set(this.state.data.slots.map(s => String(s.start)))].sort(); }
    get editable() { return !this.state.stale && this.state.data.can_edit && ["draft", "changes_requested"].includes(this.state.data.schedule.state); }
    slotAt(court, time) { return this.state.data.slots.find(s => s.court_id === court && String(s.start) === time); }
    assignment(slot) { return slot && this.state.data.assignments.find(a => a.slot_id === slot.id); }
    scheduleStateLabel(value) {
        return {draft: _t('Draft'), changes_requested: _t('Changes requested'), submitted: _t('Submitted'),
            approved: _t('Approved'), published: _t('Published'), superseded: _t('Replaced'),
            cancelled: _t('Cancelled')}[value] || _t('Status unavailable');
    }
    fixtureIssues(id) {
        const validation = this.state.data.explanation.validation;
        const assignment = this.state.data.assignments.find(item => item.fixture_id === id);
        return [...validation.errors, ...validation.warnings].filter(issue =>
            issue.fixture_id === id || (issue.fixture_ids || []).includes(id) ||
            (assignment && issue.slot_id === assignment.slot_id) ||
            (!issue.fixture_id && !issue.fixture_ids && !issue.slot_id));
    }
    selectedFixtureIssues() {
        return this.state.fixture ? this.fixtureIssues(Number(this.state.fixture)) : [];
    }
    fixtureName(id) { return this.state.data.fixtures.find(f => f.id === id)?.name || String(id); }
    fixtureSelected(id) { return this.state.fixture === `${id}`; }
    eventTime(value) { return formatEventTime(value, this.state.data.timezone || 'UTC'); }
    slotName(id) { const s = this.state.data.slots.find(s => s.id === id); return s ? `${s.court_name} / ${this.eventTime(s.start)}` : _t("Unassigned"); }
    constraintName(kind) { return ({team_window: _t('Team unavailable'), court_window: _t('Court unavailable'), minimum_rest: _t('Mandatory minimum rest for all teams')})[kind] || kind; }
    stageName(id) { return this.state.data.stages.find(s => s.id === id)?.name || String(id); }
    destination(slot) { if (!slot) return null; return this.state.destinations?.slots.find(row => row.slot_id === slot.id); }
    destinationLabel(slot) { return _t(destinationLabel(this.destination(slot))); }
    get canApply() { return !this.state.stale && !this.state.busy && canApply(this.state.preview, this.state.reason); }
    get canCompare() { return comparable(this.state.candidateA, this.state.preview); }
    async selectFixture(id) {
        if (!this.editable || this.state.busy) return;
        this.state.fixture = String(id || ''); this.state.destinations = null; this.state.selectedSlot = null;
        if (!id) return;
        await this.run(async () => {
            this.state.destinations = await this.orm.call('federation.visual.planning', 'destinations',
                [this.id, Number(id), this.state.data.signature]);
            this.state.announcement = _t('Destinations assessed. Select a slot to inspect mandatory rules and preferences.');
        });
    }
    fixtureChanged(event) { return this.selectFixture(event.target.value); }
    dragFixture(event, id) {
        if (!this.editable || this.state.busy) { event.preventDefault(); return; }
        event.dataTransfer.setData('text/plain', String(id)); event.dataTransfer.effectAllowed = 'move';
        if (Number(this.state.fixture) !== id) this.selectFixture(id);
    }
    dragOver(event) { if (this.editable) { event.preventDefault(); event.dataTransfer.dropEffect = 'move'; } }
    dropFixture(event, slot) {
        event.preventDefault();
        if (Number(event.dataTransfer.getData('text/plain')) !== Number(this.state.fixture)) return;
        return this.chooseSlot(slot);
    }
    slotKey(event) {
        if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key)) return;
        const buttons = [...this.root.el.querySelectorAll('[data-destination-button]')];
        const index = buttons.indexOf(event.currentTarget); if (index < 0) return;
        const cells = buttons.map(button => ({row: button.closest('tr').rowIndex, column: button.closest('td').cellIndex}));
        const target = navigationTarget(cells, index, event.key);
        event.preventDefault(); buttons[target]?.focus();
    }
    async chooseSlot(slot) {
        if (!slot || !this.editable) return;
        this.state.selectedSlot = slot.id;
        const assessment = this.destination(slot);
        if (!assessment || this.state.busy) { this.state.announcement = _t('Choose a fixture and wait for destination assessment.'); return; }
        if (!assessment.valid) { this.state.announcement = _t('This destination is blocked. Read the mandatory-rule explanation.'); return; }
        return this.preview('move', slot.id);
    }
    rememberCandidate() {
        if (!this.state.preview) return;
        this.state.candidateA = clone(this.state.preview); this.state.comparison = null;
        this.state.announcement = _t('Candidate A retained. Preview another candidate without applying or changing settings.');
    }
    async compareCandidates() { await this.run(async () => {
        if (!this.canCompare) return;
        this.state.comparison = await this.orm.call('federation.visual.planning', 'compare',
            [this.state.candidateA.id, this.state.preview.id]);
    }); }
    chooseCandidateA() {
        if (!this.canCompare) return;
        const current = clone(this.state.preview); this.state.preview = clone(this.state.candidateA);
        this.state.candidateA = current; this.state.comparison = null;
    }
    async preview(operation, slot = false) { await this.run(async () => {
        this.state.preview = await this.orm.call("federation.visual.planning", "preview", [this.id, operation, Number(this.state.fixture), slot, this.state.data.signature]);
    }); }
    async apply() { if (!this.canApply) return; await this.run(async () => {
        this.state.data = await this.orm.call("federation.visual.planning", "apply", [this.state.preview.id, this.state.reason]);
        this.state.preview = null; this.state.destinations = null; this.state.candidateA = null; this.state.comparison = null;
    }); }
    async configure() { await this.run(async () => {
        this.state.data = await this.orm.call("federation.visual.planning", "configure", [this.id, this.state.data.schedule.revision, clone(this.state.data.config)]);
        this.state.preview = null; this.state.destinations = null; this.state.candidateA = null; this.state.comparison = null;
    }); }
    async addConstraint() { await this.run(async () => {
        const c = this.state.constraint;
        const values = { name: c.name, kind: c.kind, minutes: Number(c.minutes),
            team_id: Number(c.team_id) || false, court_id: Number(c.court_id) || false,
            start: c.kind === "minimum_rest" ? false : c.start || false,
            end: c.kind === "minimum_rest" ? false : c.end || false };
        this.state.data = await this.orm.call("federation.visual.planning", "create_event_constraint",
            [this.id, this.state.data.schedule.revision, values]); this.state.preview = null; this.state.destinations = null; this.state.candidateA = null; this.state.comparison = null;
    }); }
    async removeConstraint(id) { await this.run(async () => {
        await this.orm.unlink("federation.visual.constraint", [id]);
        this.state.data = await this.orm.call("federation.visual.planning", "load", [this.id]); this.state.preview = null; this.state.destinations = null; this.state.candidateA = null; this.state.comparison = null;
    }); }
    async amend() { await this.run(async () => {
        const action = await this.orm.call("federation.visual.planning", "amend", [this.id, this.state.reason]);
        await this.action.doAction(action);
    }); }
    async returnRecord() { await this.action.doAction({ type: "ir.actions.act_window", res_model: "federation.schedule",
        res_id: this.id, views: [[false, "form"]], target: "current" }); }
    async openFixture(id) { await this.action.doAction({ type: "ir.actions.act_window", res_model: "federation.fixture",
        res_id: id, views: [[false, "form"]], target: "current" }); }
}
registry.category("actions").add("federation_run_court", CourtWorkspace);
registry.category("actions").add("federation_visual_plan", VisualPlan);
