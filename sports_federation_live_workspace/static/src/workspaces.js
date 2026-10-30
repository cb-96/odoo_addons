/** @odoo-module **/
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";
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
            pending: [], busy: false, dirty: false, status: _t("Not checked"), error: "", conflict: false });
        this.storagePrefix = `sf-court:v1:${session.db}:${session.uid}:`;
        this.online = () => { if (this.state.pending.length) this.sync(); };
        this.unload = (event) => { if (this.state.dirty || this.state.pending.length) {
            event.preventDefault(); event.returnValue = "";
        }};
        window.addEventListener("online", this.online);
        window.addEventListener("beforeunload", this.unload);
        onWillUnmount(() => {
            window.removeEventListener("online", this.online);
            window.removeEventListener("beforeunload", this.unload);
        });
        onWillStart(async () => {
            try { this.state.courts = await this.orm.call("federation.court.commands", "courts", []); }
            catch (error) { this.state.error = this.message(error); }
        });
    }
    message(error) { return error?.data?.message || error?.message || _t("Operation failed. Local evidence retained."); }
    get access() { return this.state.courts[Number(this.state.selected)]; }
    get storageKey() { return `${this.storagePrefix}${this.access.matchday_id}:${this.access.court_id}:${this.state.match.match_id}`; }
    get locked() { return this.state.match && (this.state.match.submitted || this.state.match.closed || !["draft", "corrected"].includes(this.state.match.result_state)); }
    async chooseCourt(event) {
        if (this.state.pending.length || this.state.dirty) { this.state.error = _t("Save or synchronise this match first."); return; }
        this.state.selected = event.target.value;
        this.state.match = null;
        if (this.state.selected === "") return;
        try { this.state.board = await this.orm.call("federation.court.commands", "load", [this.access.matchday_id, this.access.court_id]); }
        catch (error) { this.state.error = this.message(error); }
    }
    async openMatch(id) {
        if (this.state.pending.length || this.state.dirty) { this.state.error = _t("Save or synchronise this match first."); return; }
        this.state.busy = true;
        try {
            const result = await this.orm.call("federation.court.commands", "open_match", [this.access.matchday_id, this.access.court_id, id]);
            this.state.match = result;
            this.state.draft = clone(result.payload);
            this.state.conflict = result.signature !== result.draft_signature;
            const cached = JSON.parse(localStorage.getItem(this.storageKey) || "null");
            this.state.pending = cached?.pending || [];
            if (this.state.pending.length && cached?.base) {
                this.state.match.revision = cached.base.revision;
                this.state.match.signature = cached.base.signature;
            }
            if (cached?.draft) this.state.draft = cached.draft;
            this.state.dirty = Boolean(cached?.dirty);
            this.state.status = (this.state.pending.length || this.state.dirty) ? _t("Unsynchronised: stored on this device") : result.submitted ? _t("Submitted: awaiting result review") : _t("Saved on server");
            this.state.error = this.state.conflict ? _t("The published slot or canonical result changed. Reconcile explicitly.") : "";
        } catch (error) { this.state.error = this.message(error); }
        finally { this.state.busy = false; }
    }
    persist() {
        try { localStorage.setItem(this.storageKey, JSON.stringify({ draft: clone(this.state.draft),
            pending: clone(this.state.pending), dirty: this.state.dirty, base: clone(this.state.match) })); }
        catch (error) { this.state.error = _t("Device storage failed. Export evidence before leaving this screen."); throw error; }
    }
    edited() { this.state.dirty = true; this.state.status = _t("Unsynchronised edits: stored on this device"); this.persist(); }
    score(side, amount) {
        if (this.locked || this.state.busy) return;
        this.state.draft[side] = Math.max(0, this.state.draft[side] + amount); this.edited();
    }
    setScore(side, event) { this.state.draft[side] = Number(event.target.value); this.edited(); }
    addPeriod() { this.state.draft.periods.push({ home: 0, away: 0 }); this.retotal(); }
    removePeriod(index) { this.state.draft.periods.splice(index, 1); this.retotal(); }
    periodScore(index, side, event) { this.state.draft.periods[index][side] = Number(event.target.value); this.retotal(); }
    retotal() {
        const periods = this.state.draft.periods;
        this.state.draft.home = periods.reduce((sum, p) => sum + (this.state.match.mode === "sets" ? Number(p.home > p.away) : p.home), 0);
        this.state.draft.away = periods.reduce((sum, p) => sum + (this.state.match.mode === "sets" ? Number(p.away > p.home) : p.away), 0);
        this.edited();
    }
    async command(operation) {
        if (this.locked || this.state.busy || this.state.conflict) return;
        if (operation === "submit" && !window.confirm(_t("Submit this result for review? It will become read-only."))) return;
        if (operation === "undo" && this.state.pending.length) { this.state.error = _t("Synchronise pending commands before server undo."); return; }
        if (this.state.pending.some(c => c.operation === "submit")) {
            this.state.error = _t("A submission is already queued. Synchronise it before further changes."); return;
        }
        if (this.state.pending.length >= 100) {
            this.state.error = _t("Synchronise or export this device journal before adding more commands."); return;
        }
        const revision = this.state.match.revision + this.state.pending.length;
        const command = { key: key(), revision, operation, payload: clone(this.state.draft), signature: this.state.match.signature };
        this.state.pending.push(command);
        this.state.dirty = false;
        this.persist();
        this.state.status = _t("Unsynchronised: stored on this device");
        if (navigator.onLine) await this.sync();
    }
    async sync() {
        if (!this.state.match || !this.state.pending.length || this.state.busy || this.state.conflict) return;
        this.state.busy = true;
        try {
            const result = await this.orm.call("federation.court.commands", "sync", [this.access.matchday_id,
                this.access.court_id, this.state.match.match_id, clone(this.state.pending)]);
            const config = this.state.match;
            this.state.match = { ...config, ...result.current };
            this.state.pending = [];
            this.state.draft = clone(result.current.payload);
            this.state.dirty = false;
            this.state.error = "";
            this.state.status = result.current.submitted ? _t("Submitted: awaiting result review") : _t("Saved on server");
            this.persist();
            this.state.board = await this.orm.call("federation.court.commands", "load", [this.access.matchday_id, this.access.court_id]);
        } catch (error) {
            this.state.error = this.message(error);
            this.state.status = _t("Unsynchronised: retry or reconcile; evidence retained");
            // Validation/access errors are not transient connectivity failures.
            if (error?.data) this.state.conflict = true;
        } finally { this.state.busy = false; }
    }
    exportEvidence() {
        const value = { schema: 1, court: this.access, match: this.state.match,
            draft: this.state.draft, pending: this.state.pending, exported_at: new Date().toISOString() };
        const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
        const link = document.createElement("a"); link.href = url; link.download = `court-evidence-${this.state.match.match_id}.json`;
        link.click(); URL.revokeObjectURL(url);
    }
    async reconcile() {
        if (!navigator.onLine || this.state.busy) return;
        this.exportEvidence();
        if (!window.confirm(_t("Evidence exported. Discard the local command queue and reload the server draft? No official result will be changed."))) return;
        localStorage.removeItem(this.storageKey);
        const id = this.state.match.match_id;
        this.state.pending = []; this.state.dirty = false; this.state.conflict = false;
        await this.openMatch(id);
    }
    async acknowledge() {
        const reason = window.prompt(_t("Explain why this draft remains valid after the schedule/result change:"));
        if (!reason?.trim()) return;
        try {
            const result = await this.orm.call("federation.court.commands", "reconcile", [this.access.matchday_id,
                this.access.court_id, this.state.match.match_id, this.state.match.revision, reason]);
            this.state.match = { ...this.state.match, ...result }; this.state.conflict = false;
            this.state.error = ""; this.persist();
        } catch (error) { this.state.error = this.message(error); }
    }
    async nextMatch() {
        if (this.state.pending.length || this.state.dirty) return;
        const queue = this.state.board.queue;
        const index = queue.findIndex(m => m.id === this.state.match?.match_id);
        const next = queue.slice(index + 1).find(m => !["submitted", "verified", "approved"].includes(m.result_state));
        if (next) await this.openMatch(next.id);
    }
}

export class VisualPlan extends Component {
    static template = "sports_federation_live_workspace.Plan";
    static props = ["*"];
    setup() {
        this.orm = useService("orm"); this.action = useService("action");
        this.id = this.props.action.params?.schedule_id || this.props.action.context?.active_id;
        this.state = useState({ data: null, preview: null, fixture: "", reason: "", error: "", busy: false,
            constraint: { name: "", kind: "team_window", team_id: "", court_id: "", start: "", end: "", minutes: 0 } });
        onWillStart(() => this.refresh());
    }
    async run(callback) {
        if (this.state.busy) return;
        this.state.busy = true; this.state.error = "";
        try { return await callback(); } catch (error) { this.state.error = error?.data?.message || error.message; }
        finally { this.state.busy = false; }
    }
    async refresh() { await this.run(async () => {
        this.state.data = await this.orm.call("federation.visual.planning", "load", [this.id]); this.state.preview = null;
    }); }
    get courts() { return [...new Map(this.state.data.slots.map(s => [s.court_id, { id: s.court_id, name: s.court_name }])).values()]; }
    get times() { return [...new Set(this.state.data.slots.map(s => String(s.start)))].sort(); }
    get editable() { return ["draft", "changes_requested"].includes(this.state.data.schedule.state); }
    slotAt(court, time) { return this.state.data.slots.find(s => s.court_id === court && String(s.start) === time); }
    assignment(slot) { return slot && this.state.data.assignments.find(a => a.slot_id === slot.id); }
    fixtureName(id) { return this.state.data.fixtures.find(f => f.id === id)?.name || String(id); }
    slotName(id) { const s = this.state.data.slots.find(s => s.id === id); return s ? `${s.court_name} / ${s.start}` : _t("Unassigned"); }
    async preview(operation, slot = false) { await this.run(async () => {
        this.state.preview = await this.orm.call("federation.visual.planning", "preview", [this.id, operation, Number(this.state.fixture), slot]);
    }); }
    async apply() { await this.run(async () => {
        this.state.data = await this.orm.call("federation.visual.planning", "apply", [this.state.preview.id, this.state.reason]);
        this.state.preview = null;
    }); }
    async configure() { await this.run(async () => {
        this.state.data = await this.orm.call("federation.visual.planning", "configure", [this.id, this.state.data.schedule.revision, clone(this.state.data.config)]);
        this.state.preview = null;
    }); }
    async addConstraint() { await this.run(async () => {
        const c = this.state.constraint;
        const values = { schedule_id: this.id, name: c.name, kind: c.kind, minutes: Number(c.minutes),
            team_id: Number(c.team_id) || false, court_id: Number(c.court_id) || false,
            start: c.start ? new Date(c.start).toISOString().slice(0, 19).replace("T", " ") : false,
            end: c.end ? new Date(c.end).toISOString().slice(0, 19).replace("T", " ") : false };
        await this.orm.create("federation.visual.constraint", [values]);
        this.state.data = await this.orm.call("federation.visual.planning", "load", [this.id]); this.state.preview = null;
    }); }
    async removeConstraint(id) { await this.run(async () => {
        await this.orm.unlink("federation.visual.constraint", [id]);
        this.state.data = await this.orm.call("federation.visual.planning", "load", [this.id]); this.state.preview = null;
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
