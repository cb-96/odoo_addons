// Offline court app. Plain ES modules: it starts without the Odoo web client,
// so it also starts without a network once the service worker stored it.

import { Api, ApiError, NetworkError } from "./lib/api.js";
import {
    adoptLegacy, clone, isLocked, legacyJournals, markConflict, queueCapture,
    queueSide, rebase, resetToServer, status, validateJournal,
} from "./lib/journal.js";
import { MatchLock } from "./lib/lock.js";
import { draftProblems, isDraw, OUTCOMES, participation, totals } from "./lib/policy.js";
import { requestPersistence, Store } from "./lib/store.js";
import { refreshPack, syncAll, syncJournal } from "./lib/sync.js";

const root = document.getElementById("court-app");
const SYNC_EVERY_MS = 30000;
const STALE_AFTER_MS = 15 * 60 * 1000;

const STATUS_TEXT = {
    not_started: "Not started",
    saved: "Saved on server",
    draft: "Changed on this phone",
    waiting: "Waiting to send",
    submit_waiting: "Submission waiting to send",
    submitted: "Submitted · waiting for approval",
    approved: "Approved",
    contested: "Returned for correction",
    conflict: "Conflict · action needed",
};
const OUTCOME_TEXT = {
    normal: "Played normally",
    forfeit_home: "Home team forfeits",
    forfeit_away: "Away team forfeits",
    interrupted: "Interrupted (coordinator review)",
    abandoned: "Abandoned (coordinator review)",
    disputed: "Disputed (coordinator review)",
};
const LOG_TEXT = {
    card_blue: "Blue card",
    card_yellow: "Yellow card",
    card_red: "Red card",
    team_card_yellow: "Team yellow card",
    team_card_red: "Team red card",
    staff_card_yellow: "Staff yellow card",
    staff_card_red: "Staff red card",
    timeout: "Time-out",
    challenge: "Challenge",
};
const ROLE_TEXT = {
    head_referee: "Head referee",
    assistant_referee: "Assistant referee",
    club_scorer: "Club scorer",
    court_operator: "Court operator",
};

const state = {
    store: null,
    api: null,
    token: null,
    pack: null,
    journals: new Map(),
    view: "loading",
    matchId: null,
    online: navigator.onLine,
    lastSync: null,
    persisted: false,
    notice: null,
    error: null,
    busy: false,
    unauthorized: null,
    changes: [],
    updateReady: false,
    swActive: false,
};
const lock = new MatchLock();
let queue = Promise.resolve();

/** Serialize every journal write: the UI and the sync engine never race. */
function serial(work) {
    const run = queue.then(work, work);
    queue = run.catch(() => {});
    return run;
}

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

function time(value) {
    if (!value) return "";
    const date = new Date(value.replace(" ", "T") + "Z");
    try {
        return new Intl.DateTimeFormat(undefined, {
            hour: "2-digit", minute: "2-digit", timeZone: state.pack?.matchday?.timezone || "UTC",
        }).format(date);
    } catch {
        return value.slice(11, 16);
    }
}

function packMatch(id) {
    return state.pack?.matches.find((match) => match.id === id) || null;
}

async function loadJournals() {
    state.journals = new Map();
    for (const journal of await state.store.journals()) {
        try {
            state.journals.set(journal.match_id, validateJournal(journal));
        } catch (error) {
            state.journals.set(journal.match_id, markConflict(journal, error.message, "invalid"));
        }
    }
}

async function saveJournal(journal) {
    await state.store.saveJournal(journal);
    state.journals.set(journal.match_id, journal);
}

function pendingCount() {
    let count = 0;
    for (const journal of state.journals.values()) count += journal.pending.length + (journal.dirty ? 1 : 0);
    return count;
}

// ── Rendering ───────────────────────────────────────────────────────────
function fieldKey(element) {
    const form = element.closest("form")?.dataset.action || "";
    const d = element.dataset;
    return [form, element.name, d.action, d.sheet, d.player, d.index, d.side].join("|");
}

/**
 * Re-render without losing what the scorer is typing: a background sync can
 * re-render at any moment, so form values and focus are kept.
 */
function render() {
    const views = { loading: viewLoading, enrol: viewEnrol, home: viewHome, match: viewMatch, fatal: viewFatal };
    const kept = new Map();
    for (const element of root.querySelectorAll("form input, form select, form textarea, textarea")) {
        kept.set(fieldKey(element), element.type === "checkbox" ? element.checked : element.value);
    }
    const active = document.activeElement && root.contains(document.activeElement) ? document.activeElement : null;
    const focusKey = active ? fieldKey(active) : null;
    const selection = active && "selectionStart" in active ? [active.selectionStart, active.selectionEnd] : null;
    root.innerHTML = statusBar() + `<main>${messages()}${(views[state.view] || viewLoading)()}</main>`;
    for (const element of root.querySelectorAll("form input, form select, form textarea, textarea")) {
        const key = fieldKey(element);
        if (!kept.has(key)) continue;
        if (element.type === "checkbox") element.checked = kept.get(key);
        else element.value = kept.get(key);
    }
    const autofocus = root.querySelector("[data-autofocus]");
    if (autofocus) return autofocus.focus();
    if (focusKey) {
        const again = [...root.querySelectorAll("input, select, textarea, button")].find((el) => fieldKey(el) === focusKey);
        if (again) {
            again.focus();
            try { if (selection) again.setSelectionRange(...selection); } catch { /* Not a text field. */ }
        }
    }
    return undefined;
}

function statusBar() {
    if (["loading", "enrol", "fatal"].includes(state.view) && !state.pack) return "";
    const pending = pendingCount();
    const stale = pending && state.lastSync && Date.now() - Date.parse(state.lastSync) > STALE_AFTER_MS;
    const ready = state.pack && state.persisted && state.swActive;
    const reasons = [];
    if (!state.pack) reasons.push("no game day stored");
    if (!state.persisted) reasons.push("browser may clear stored data");
    if (!state.swActive) reasons.push("app not stored yet");
    return `<header class="bar"><div class="status ${state.online ? "" : "offline"} ${stale ? "stale" : ""}" role="status" aria-live="polite">
        <span class="dot" aria-hidden="true"></span><strong>${state.online ? "Online" : "Offline"}</strong>
        <span>· ${pending ? `${pending} change${pending > 1 ? "s" : ""} not sent` : "Everything sent"}</span>
        <span>· last sync ${state.lastSync ? esc(new Date(state.lastSync).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })) : "never"}</span>
        <span>· ${ready ? "Ready offline ✓" : `Not ready offline (${esc(reasons.join(", "))})`}</span>
        ${state.online && pending ? `<button data-action="sync">Send now</button>` : ""}
        ${state.updateReady && !pending && state.view !== "match" ? `<button data-action="update">Update app</button>` : ""}
    </div></header>`;
}

function messages() {
    let html = "";
    if (state.unauthorized) {
        html += `<div class="notice error" role="alert"><strong>${esc(state.unauthorized)}</strong><br>
            Your unsent scores stay on this phone. Export them, or prepare this phone again from
            <a href="/my/court-duties">My court duties</a> while online.</div>`;
    }
    if (state.error) html += `<div class="notice error" role="alert" tabindex="-1" data-autofocus>${esc(state.error)}</div>`;
    if (state.notice) html += `<div class="notice ok" role="status">${esc(state.notice)}</div>`;
    for (const change of state.changes) {
        const text = change.type === "moved" ? `${change.match} moved to ${time(change.start)}, ${change.court}.`
            : change.type === "added" ? `${change.match} was added to your list.`
            : `${change.match} is no longer on your list.`;
        html += `<div class="notice" role="status">${esc(text)}</div>`;
    }
    return html;
}

function viewLoading() {
    return `<p>Loading…</p>`;
}

function viewFatal() {
    return `<h1>Court scoring</h1><p>${esc(state.error || "This browser cannot run the court app.")}</p>
        <p>Use the printed scoresheet for this match.</p>`;
}

function viewEnrol() {
    return `<h1>Prepare this phone</h1>
        <p>Open <a href="/my/court-duties" class="btn primary">My court duties</a> while you are online and logged in,
        then choose <strong>Prepare this phone</strong> for your game day.</p>
        <p class="muted">The phone then keeps your matches and works without a network on the game day.</p>`;
}

function viewHome() {
    const pack = state.pack;
    const known = new Set(pack.matches.map((match) => match.id));
    const orphans = [...state.journals.values()].filter((journal) => !known.has(journal.match_id));
    return `<h1>${esc(pack.matchday.name)}</h1>
        <p class="muted">${esc(pack.matchday.venue)} · ${esc(pack.device.user)} · ${esc(pack.device.label)}</p>
        ${pack.matches.length ? "" : `<p>You have no matches to score on this game day.</p>`}
        ${pack.matches.map(matchCard).join("")}
        ${orphans.map((journal) => `<div class="card"><strong>Match #${journal.match_id}</strong>
            <p>${esc(journal.conflict?.message || "No longer on your list.")}</p>
            <button data-action="export" data-match="${journal.match_id}">Export scores</button></div>`).join("")}
        <div class="actions">
            ${state.online ? `<button data-action="refresh">Refresh game day</button>` : ""}
            <button data-action="export-all">Export everything</button>
            <button class="danger" data-action="forget">Remove this phone</button>
        </div>`;
}

function matchCard(match) {
    const journal = state.journals.get(match.id);
    const code = status(journal);
    return `<div class="card"><button class="open" data-action="open" data-match="${match.id}">
        <div class="row"><strong>${esc(time(match.start))}</strong><span>${esc(match.court)}</span>
        <span class="chip ${code}">${esc(STATUS_TEXT[code])}</span></div>
        <div>${esc(match.home)} – ${esc(match.away)}</div>
        <div class="muted">${esc(ROLE_TEXT[match.source] || "")}</div></button></div>`;
}

function viewMatch() {
    const match = packMatch(state.matchId);
    const journal = state.journals.get(state.matchId);
    if (!match || !journal) return `<p>This match is not on this phone.</p><button data-action="home">Back</button>`;
    const scoring = match.scoring;
    const locked = isLocked(journal);
    const draft = journal.draft;
    const sum = totals(draft.periods || [], scoring);
    const problems = draftProblems({ ...draft, ...(scoring.mode === "aggregate" ? {} : sum) }, scoring, false);
    const conflict = journal.conflict;
    const otherPhone = conflict?.message?.includes("another phone") || Boolean(journal.server.device_id && !journal.server.this_device);
    return `<button data-action="home">← All matches</button>
        <h1>${esc(match.home)} – ${esc(match.away)}</h1>
        <p class="muted">${esc(time(match.start))} · ${esc(match.court)} · ${esc(ROLE_TEXT[match.source] || "")}
        · <span class="chip ${status(journal)}">${esc(STATUS_TEXT[status(journal)])}</span></p>
        ${conflict ? `<div class="notice error" role="alert"><strong>Conflict:</strong> ${esc(conflict.message)}
            <div class="actions"><button data-action="export" data-match="${match.id}">Export scores</button>
            ${state.online && otherPhone ? `<button class="primary" data-action="claim">Take over on this phone</button>` : ""}
            ${state.online ? `<button data-action="keep-server">Keep the server version</button>` : ""}</div></div>` : ""}
        ${!conflict && otherPhone && !locked ? `<div class="notice">Another phone scores this match.
            ${state.online ? `<button data-action="claim">Take over on this phone</button>` : "Connect to take it over."}</div>` : ""}
        ${locked ? `<div class="notice ok">This result is submitted and waits for the tournament manager. It can no longer be changed here.</div>` : ""}
        ${scoreSection(match, journal, locked, sum)}
        ${problems.length && !locked ? `<div class="notice">${problems.map(esc).join("<br>")}</div>` : ""}
        ${lineupSection(match, journal, locked)}
        ${logSection(match, journal, locked)}
        ${locked ? "" : submitSection(match, journal)}
        <div class="actions"><button data-action="export" data-match="${match.id}">Export scores</button></div>`;
}

function scoreSection(match, journal, locked, sum) {
    const scoring = match.scoring;
    const draft = journal.draft;
    const disabled = locked || journal.conflict ? "disabled" : "";
    if (scoring.mode === "aggregate") {
        return `<h2>Score</h2><div class="row">
            ${scoreInput("home", null, draft.home, disabled, match.home)}
            ${scoreInput("away", null, draft.away, disabled, match.away)}</div>`;
    }
    const [win, draw] = scoring.set_points || [1, 0];
    const label = scoring.mode === "sets" ? "Sets" : "Periods";
    return `<h2>${label}</h2>
        ${scoring.mode === "sets" ? `<p class="muted">Won set ${win} point${win === 1 ? "" : "s"}, drawn set ${draw} each.</p>` : ""}
        ${(draft.periods || []).map((period, index) => `<div class="set card">
            <div class="set-head"><strong>${scoring.mode === "sets" ? "Set" : "Period"} ${index + 1}</strong>
            ${scoring.mode === "sets" && isDraw(period) ? `<span class="chip">Draw</span>` : ""}
            <button class="remove" data-action="remove-set" data-index="${index}" ${disabled} aria-label="Remove ${label.toLowerCase()} ${index + 1}">✕</button></div>
            <div class="set-scores">${scoreInput("home", index, period.home, disabled, match.home)}
            <span aria-hidden="true">–</span>
            ${scoreInput("away", index, period.away, disabled, match.away)}</div></div>`).join("")}
        <button data-action="add-set" ${disabled || (draft.periods || []).length >= (scoring.max_periods || 100) ? "disabled" : ""}>Add ${scoring.mode === "sets" ? "set" : "period"}</button>
        <div class="totals" aria-live="polite">${sum.home} – ${sum.away}</div>`;
}

function scoreInput(side, index, value, disabled, team) {
    const attrs = `data-side="${side}" ${index === null ? "" : `data-index="${index}"`}`;
    return `<div class="score" role="group" aria-label="${esc(team)}"><span class="team">${esc(team)}</span>
        <button data-action="dec" ${attrs} ${disabled} aria-label="${esc(team)} minus one">−</button>
        <input type="number" inputmode="numeric" min="0" value="${Number(value) || 0}" data-action="score" ${attrs} ${disabled} aria-label="${esc(team)}">
        <button data-action="inc" ${attrs} ${disabled} aria-label="${esc(team)} plus one">+</button></div>`;
}

function lineupSection(match, journal, locked) {
    if (!match.lineups.length) return `<h2>Line-ups</h2><p class="muted">No line-ups on this phone.</p>`;
    return `<h2>Who plays this match</h2><p class="muted">Untick the game-day players who do not play this match.</p>
        ${match.lineups.map((lineup) => {
            const crossed = journal.crossed[lineup.sheet_id] || [];
            const count = participation(lineup, crossed);
            return `<fieldset class="card lineup"><legend><strong>${esc(lineup.team)}</strong>
                · ${count.playing}${count.limit ? ` / max ${count.limit}` : ""} playing</legend>
                ${count.over ? `<p class="notice error">Too many players for this match.</p>` : ""}
                ${lineup.players.map((player) => {
                    const out = crossed.includes(player.id);
                    return `<label class="${out ? "out" : ""}"><input type="checkbox" data-action="cross" data-sheet="${lineup.sheet_id}"
                        data-player="${player.id}" ${out ? "" : "checked"} ${locked || lineup.state === "draft" ? "disabled" : ""}>
                        <strong>${esc(player.number)}</strong> ${esc(player.name)}${player.captain ? " (C)" : ""}</label>`;
                }).join("")}
                ${lineup.state === "draft" ? `<p class="muted">Line-up not submitted yet: players cannot be crossed out.</p>` : ""}
            </fieldset>`;
        }).join("")}`;
}

function logSection(match, journal, locked) {
    const players = match.lineups.flatMap((lineup) => lineup.players.map((p) => ({ ...p, side: lineup.side })));
    const name = (id) => players.find((p) => p.id === id);
    const rows = journal.log.map((event, index) => {
        const player = event.player_id ? name(event.player_id) : null;
        const team = event.side === "home" ? match.home : match.away;
        return `<li>${esc(LOG_TEXT[event.type])} · ${esc(team)}${player ? ` · ${esc(player.number)} ${esc(player.name)}` : ""}
            ${event.half ? ` · half ${event.half}` : ""}${event.set ? ` · set ${event.set}` : ""}
            ${locked ? "" : `<button data-action="remove-event" data-index="${index}" aria-label="Remove">✕</button>`}</li>`;
    }).join("");
    return `<h2>Cards, time-outs and challenges</h2>
        ${rows ? `<ul class="log">${rows}</ul>` : `<p class="muted">Nothing recorded.</p>`}
        ${locked ? "" : `<form class="card row" data-action="add-event">
            <select name="type" aria-label="What">${Object.entries(LOG_TEXT).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select>
            <select name="side" aria-label="Team"><option value="home">${esc(match.home)}</option><option value="away">${esc(match.away)}</option></select>
            <select name="player_id" aria-label="Player"><option value="">No player</option>
                ${players.map((p) => `<option value="${p.id}">${esc(p.side === "home" ? match.home : match.away)} · ${esc(p.number)} ${esc(p.name)}</option>`).join("")}</select>
            <select name="half" aria-label="Half"><option value="">Half</option><option value="1">1st half</option><option value="2">2nd half</option></select>
            <input name="set" type="number" min="1" max="100" placeholder="Set" aria-label="Set number">
            <button type="submit">Add</button></form>`}`;
}

function submitSection(match, journal) {
    const draft = journal.draft;
    const disabled = journal.conflict ? "disabled" : "";
    const head = match.source === "head_referee";
    return `<h2>Result</h2>
        <label>Outcome <select data-action="outcome" ${disabled}>${OUTCOMES.map((o) =>
            `<option value="${o}" ${draft.outcome === o ? "selected" : ""}>${esc(OUTCOME_TEXT[o])}</option>`).join("")}</select></label>
        ${draft.outcome !== "normal" ? `<p><label>Reason<br><textarea data-action="reason" rows="2" maxlength="2000" ${disabled}>${esc(draft.reason)}</textarea></label></p>` : ""}
        <div class="actions"><button data-action="save" ${disabled}>Save</button></div>
        <form class="card" data-action="submit">
            <h2>Submit to the tournament manager</h2>
            ${head ? `<label><input type="checkbox" name="self_confirm" required> I am the head referee and confirm this result.</label>`
                : `<p class="muted">Head referee${match.head_referee ? ` (${esc(match.head_referee.name)})` : ""}: enter your PIN to confirm.
                    Without it the result is sent as <em>not confirmed by the head referee</em>.</p>
                   <input name="pin" type="password" inputmode="numeric" autocomplete="off" maxlength="6" placeholder="PIN (optional)" aria-label="Head referee PIN">`}
            <div class="actions"><button class="primary" type="submit" ${disabled}>Submit result</button></div>
        </form>`;
}

// ── Actions ─────────────────────────────────────────────────────────────
/**
 * Change the journal; ``dirty`` marks an unsaved score draft.
 *
 * The screen updates at once, so fast taps on + are never lost to a
 * re-render. The same change is then applied to the stored journal in the
 * serial queue, so it never overwrites what a sync stored meanwhile.
 */
function editDraft(mutate, dirty = true) {
    const id = state.matchId;
    const match = packMatch(id);
    const apply = (journal) => {
        mutate(journal);
        if (match.scoring.mode !== "aggregate") Object.assign(journal.draft, totals(journal.draft.periods, match.scoring));
        if (dirty) journal.dirty = true;
        journal.updated_at = new Date().toISOString();
        return journal;
    };
    const shown = clone(state.journals.get(id));
    if (isLocked(shown) || shown.conflict) return Promise.resolve();
    state.journals.set(id, apply(shown));
    render();
    return serial(async () => {
        const stored = (await state.store.journal(id)) || shown;
        const saved = apply(clone(stored));
        await state.store.saveJournal(saved);
        state.journals.set(id, saved);
        state.storageFailed = false;
    }).catch((error) => {
        state.storageFailed = true;
        showError(new Error(`Not saved on this phone: ${error.message}. Keep this screen open and export.`));
    });
}

async function queue_(operation, extra = null) {
    await serial(async () => {
        let journal = state.journals.get(state.matchId);
        journal = operation === "participation" || operation === "log"
            ? queueSide(journal, operation) : queueCapture(journal, operation, extra);
        await saveJournal(journal);
    });
    state.notice = operation === "submit" ? "Submission saved on this phone." : "Saved on this phone.";
    render();
    await syncOne(state.matchId);
}

async function syncOne(matchId) {
    if (!state.online || !state.api) return;
    await serial(async () => {
        const journal = state.journals.get(matchId);
        if (!journal) return;
        const result = await syncJournal(state.store, state.api, journal);
        state.journals.set(matchId, result.journal);
        handleSyncResult(result);
    });
    render();
}

function handleSyncResult(result) {
    if (result.offline) state.online = false;
    if (result.unauthorized) state.unauthorized = result.unauthorized;
    if (result.sent) {
        state.lastSync = new Date().toISOString();
        state.notice = "Sent to the server.";
        state.store.setMeta("last_sync", state.lastSync);
    }
    if (result.conflict) state.error = result.conflict;
}

async function syncEverything() {
    if (!state.api || state.busy) return;
    state.busy = true;
    try {
        await serial(async () => {
            const summary = await syncAll(state.store, state.api);
            await loadJournals();
            if (summary.unauthorized) state.unauthorized = summary.unauthorized;
            if (summary.offline) state.online = false;
            if (!summary.offline && !summary.unauthorized) {
                state.lastSync = new Date().toISOString();
                await state.store.setMeta("last_sync", state.lastSync);
            }
            if (summary.conflicts) state.error = `${summary.conflicts} match${summary.conflicts > 1 ? "es need" : " needs"} attention.`;
        });
    } finally {
        state.busy = false;
    }
    render();
}

async function refresh() {
    if (!state.api) return;
    try {
        await serial(async () => {
            const result = await refreshPack(state.store, state.api);
            state.pack = result.pack;
            state.changes = result.changes;
            await loadJournals();
            await adoptLegacyJournals();
        });
        state.unauthorized = null;
    } catch (error) {
        if (error instanceof NetworkError) state.online = false;
        else if (error instanceof ApiError && error.status === 401) state.unauthorized = error.message;
        else state.error = error.message;
    }
    render();
}

/** Unsent scores of the backend court app on this phone: send them from here. */
async function adoptLegacyJournals() {
    if (!state.pack?.database) return;
    let found = [];
    try {
        found = legacyJournals(localStorage, state.pack.database, state.pack.device.user_id);
    } catch {
        return;
    }
    for (const legacy of found) {
        const journal = state.journals.get(legacy.match_id);
        if (!journal || journal.legacy_name === legacy.name) continue;
        await saveJournal(adoptLegacy(journal, legacy));
        state.notice = "Unsent scores from Run This Court were moved into this app.";
    }
}

function exportJournals(ids) {
    const value = {
        schema: 3,
        exported_at: new Date().toISOString(),
        device: state.pack?.device || null,
        matchday: state.pack?.matchday || null,
        journals: ids.map((id) => ({ journal: state.journals.get(id), match: packMatch(id) })),
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `court-scores-${ids.length === 1 ? ids[0] : "all"}-${Date.now()}.json`;
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function openMatch(id) {
    if (!(await lock.acquire(id))) {
        state.error = "This match is already open in another tab of this browser.";
        render();
        return;
    }
    state.view = "match";
    state.matchId = id;
    state.notice = null;
    state.error = null;
    state.changes = [];
    render();
}

async function claim() {
    try {
        const current = await state.api.claim(state.matchId);
        await serial(async () => saveJournal(rebase(state.journals.get(state.matchId), current)));
        state.notice = "This phone now scores the match.";
        state.error = null;
        await syncOne(state.matchId);
    } catch (error) {
        state.error = error.message;
    }
    render();
}

async function keepServer() {
    exportJournals([state.matchId]);
    if (!window.confirm("Your scores were exported. Replace them on this phone with the server version?")) return;
    await refresh();
    const match = packMatch(state.matchId);
    if (!match) return;
    await serial(async () => saveJournal(resetToServer(state.journals.get(state.matchId), match)));
    state.notice = "The server version is shown.";
    render();
}

async function forget() {
    if (pendingCount() && !window.confirm("Some changes are not sent. Export them first? Press Cancel to export.")) {
        exportJournals([...state.journals.keys()]);
        return;
    }
    if (!window.confirm("Remove this phone? It can no longer send scores and its stored data is deleted.")) return;
    try { await state.api?.forget(); } catch { /* Offline: the token expires anyway. */ }
    await state.store.wipe();
    location.replace("/court/app");
}

async function onClick(event) {
    const target = event.target.closest("[data-action]");
    if (!target || target.tagName === "FORM" || target.tagName === "SELECT" || target.tagName === "TEXTAREA") return undefined;
    if (target.tagName === "INPUT" && target.type !== "checkbox") return undefined;
    const action = target.dataset.action;
    const index = target.dataset.index !== undefined ? Number(target.dataset.index) : null;
    const side = target.dataset.side;
    state.error = action === "cross" ? state.error : null;
    switch (action) {
        case "open": return openMatch(Number(target.dataset.match));
        case "home": await lock.releaseAll(); state.view = "home"; state.matchId = null; state.notice = null; return render();
        case "sync": return syncEverything();
        case "refresh": return refresh();
        case "update": return activateUpdate();
        case "export": return exportJournals([Number(target.dataset.match)]);
        case "export-all": return exportJournals([...state.journals.keys()]);
        case "forget": return forget();
        case "claim": return claim();
        case "keep-server": return keepServer();
        case "save": return queue_("save");
        case "add-set": return editDraft((j) => j.draft.periods.push({ home: 0, away: 0 }));
        case "remove-set": return editDraft((j) => j.draft.periods.splice(index, 1));
        case "inc":
        case "dec": return editDraft((j) => {
            const delta = action === "inc" ? 1 : -1;
            const holder = index === null ? j.draft : j.draft.periods[index];
            holder[side] = Math.max(0, (Number(holder[side]) || 0) + delta);
        });
        case "remove-event":
            await editDraft((j) => j.log.splice(index, 1), false);
            return queue_("log");
        case "cross": {
            const sheet = target.dataset.sheet;
            const player = Number(target.dataset.player);
            const checked = target.checked;
            await editDraft((j) => {
                const list = new Set(j.crossed[sheet] || []);
                if (checked) list.delete(player); else list.add(player);
                j.crossed[sheet] = [...list].sort((a, b) => a - b);
            }, false);
            return queue_("participation");
        }
        default: return undefined;
    }
}

async function onChange(event) {
    const target = event.target;
    const action = target.dataset?.action;
    if (action === "score") {
        const index = target.dataset.index !== undefined ? Number(target.dataset.index) : null;
        const value = Math.max(0, Math.floor(Number(target.value) || 0));
        return editDraft((j) => { (index === null ? j.draft : j.draft.periods[index])[target.dataset.side] = value; });
    }
    if (action === "outcome") return editDraft((j) => { j.draft.outcome = target.value; });
    if (action === "reason") return editDraft((j) => { j.draft.reason = target.value.slice(0, 2000); });
    return undefined;
}

async function onSubmit(event) {
    const form = event.target;
    event.preventDefault();
    const data = new FormData(form);
    if (form.dataset.action === "add-event") {
        const value = (name) => (data.get(name) ? Number(data.get(name)) : null);
        const type = data.get("type");
        const needsPlayer = ["card_blue", "card_yellow", "card_red"].includes(type);
        if (needsPlayer && !value("player_id")) { state.error = "Choose the player for this card."; return render(); }
        form.reset();
        await editDraft((j) => j.log.push({
            type, side: data.get("side"), player_id: needsPlayer ? value("player_id") : null,
            half: value("half"), set: value("set"), note: "",
        }), false);
        return queue_("log");
    }
    if (form.dataset.action === "submit") {
        const journal = state.journals.get(state.matchId);
        const match = packMatch(state.matchId);
        const problems = draftProblems(journal.draft, match.scoring, true);
        if (problems.length) { state.error = problems.join(" "); return render(); }
        let confirmation = null;
        if (match.source === "head_referee") confirmation = { method: "self" };
        else if ((data.get("pin") || "").trim()) confirmation = { method: "pin", pin: data.get("pin").trim() };
        else if (!window.confirm("Submit without the head referee's PIN? The result is marked as not confirmed.")) return undefined;
        if (journal.dirty) await queue_("save");
        return queue_("submit", confirmation);
    }
    return undefined;
}

// ── Service worker and lifecycle ───────────────────────────────────────
async function registerWorker() {
    if (!("serviceWorker" in navigator)) return;
    try {
        const registration = await navigator.serviceWorker.register("/court/sw.js", { scope: "/court/" });
        state.swActive = Boolean(navigator.serviceWorker.controller || registration.active);
        const watch = (worker) => worker?.addEventListener("statechange", () => {
            if (worker.state === "installed" && navigator.serviceWorker.controller) { state.updateReady = true; render(); }
            if (worker.state === "activated") { state.swActive = true; render(); }
        });
        if (registration.waiting && navigator.serviceWorker.controller) state.updateReady = true;
        watch(registration.installing);
        registration.addEventListener("updatefound", () => watch(registration.installing));
        navigator.serviceWorker.addEventListener("controllerchange", () => {
            if (state.reloadOnUpdate) location.reload();
            state.swActive = true;
        });
        state.registration = registration;
    } catch {
        state.swActive = false;
    }
}

function activateUpdate() {
    if (pendingCount() || state.view === "match") return;
    state.reloadOnUpdate = true;
    state.registration?.waiting?.postMessage({ type: "activate-update" });
}

async function activateFromCode(code) {
    history.replaceState(null, "", "/court/app");
    const result = await new Api(null).activate(code);
    if (state.token && state.token !== result.token) {
        // A new preparation replaces the previous device on this phone.
        for (const journal of state.journals.values()) {
            if (journal.pending.length || journal.dirty) {
                throw new Error("This phone still has unsent scores from the previous preparation. Export or send them first.");
            }
        }
        await state.store.wipe();
        state.journals = new Map();
    }
    state.token = result.token;
    await state.store.setMeta("token", result.token);
}

/** After the game day, wipe stored data once everything was sent. */
async function cleanupFinishedDay() {
    const pack = state.pack;
    if (!pack) return;
    const expired = Date.parse(pack.device.expires_at.replace(" ", "T") + "Z") < Date.now();
    const dirty = [...state.journals.values()].some((j) => j.pending.length || j.dirty || j.conflict);
    if (expired && !dirty) {
        await state.store.wipe();
        state.pack = null;
        state.token = null;
        state.journals = new Map();
        state.notice = "The game day has ended. Its data was removed from this phone.";
        state.view = "enrol";
    }
}

/** Activate a one-time code from the address, then load the game day. */
async function start() {
    const code = new URLSearchParams(location.hash.slice(1)).get("code");
    if (code) {
        try {
            await activateFromCode(code);
            state.notice = "This phone is prepared for your game day.";
        } catch (error) {
            state.error = error instanceof NetworkError ? "No connection: connect and open My court duties again." : error.message;
        }
    }
    if (!state.token) {
        state.view = "enrol";
        return render();
    }
    state.api = new Api(state.token);
    state.unauthorized = null;
    if (navigator.onLine) {
        await refresh();
        await syncEverything();
    }
    await cleanupFinishedDay();
    if (["loading", "enrol"].includes(state.view)) state.view = state.pack ? "home" : "enrol";
    return render();
}

function showError(error) {
    state.error = error?.message || String(error);
    render();
}

async function boot() {
    root.addEventListener("click", (event) => onClick(event).catch(showError));
    root.addEventListener("change", (event) => onChange(event).catch(showError));
    root.addEventListener("submit", (event) => onSubmit(event).catch(showError));
    window.addEventListener("online", () => { state.online = true; refresh().then(syncEverything); });
    window.addEventListener("offline", () => { state.online = false; render(); });
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible" && navigator.onLine) syncEverything();
    });
    window.addEventListener("beforeunload", (event) => {
        if ([...state.journals.values()].some((j) => j.dirty)) { event.preventDefault(); event.returnValue = ""; }
    });
    registerWorker();
    try {
        state.store = await Store.open();
    } catch (error) {
        state.view = "fatal";
        state.error = error.message;
        return render();
    }
    state.persisted = await requestPersistence();
    state.token = await state.store.meta("token");
    state.pack = await state.store.pack();
    state.lastSync = await state.store.meta("last_sync");
    await loadJournals();
    // The app may already be open when a new preparation link arrives.
    window.addEventListener("hashchange", () => start().catch(showError));
    await start();
    setInterval(() => {
        if (navigator.onLine && document.visibilityState === "visible") syncEverything();
    }, SYNC_EVERY_MS);
    return undefined;
}

boot().catch(showError);
