// Per-match journal kept on the phone. Pure functions: the store saves the
// returned objects, the sync engine sends ``pending`` in order.
//
// Capture commands (save/undo/submit) carry the revision they expect on the
// server: the confirmed base revision plus the capture commands queued
// before them. Side commands (participation, log) are full-state and
// idempotent, so only the newest unsent one of each kind is kept.

export const MAX_PENDING = 100;
const CAPTURE = new Set(["save", "undo", "submit"]);
const SIDE = new Set(["participation", "log"]);

export const clone = (value) => JSON.parse(JSON.stringify(value));

export function newKey() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    const bytes = new Uint8Array(16);
    globalThis.crypto.getRandomValues(bytes);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function crossedOutFromPack(match) {
    const crossed = {};
    for (const lineup of match.lineups || []) {
        crossed[lineup.sheet_id] = lineup.players.filter((p) => p.crossed_out).map((p) => p.id);
    }
    return crossed;
}

export function newJournal(match, matchdayId) {
    return {
        schema: 3,
        match_id: match.id,
        matchday_id: matchdayId,
        base: { revision: match.capture.revision, signature: match.signature },
        draft: clone(match.capture.payload),
        log: clone(match.capture.match_log || []),
        crossed: crossedOutFromPack(match),
        pending: [],
        dirty: false,
        conflict: null,
        server: {
            result_state: match.result_state,
            submitted: match.capture.submitted,
            closed: match.capture.closed,
            device_id: match.capture.device_id || false,
            this_device: Boolean(match.capture.this_device),
        },
        updated_at: new Date().toISOString(),
    };
}

export function capturePending(journal) {
    return journal.pending.filter((command) => CAPTURE.has(command.operation));
}

export function isLocked(journal) {
    return Boolean(
        journal.server.submitted
            || journal.server.closed
            || !["draft", "corrected"].includes(journal.server.result_state)
            || journal.pending.some((command) => command.operation === "submit")
    );
}

export function validateJournal(journal) {
    if (!journal || typeof journal !== "object" || !journal.draft || !Array.isArray(journal.pending)) {
        throw new Error("Invalid journal on this phone. Export it before doing anything else.");
    }
    if (journal.pending.length > MAX_PENDING) throw new Error("Too many unsent changes.");
    const keys = new Set();
    for (const command of journal.pending) {
        if (!command || typeof command.key !== "string" || keys.has(command.key)
            || !(CAPTURE.has(command.operation) || SIDE.has(command.operation))) {
            throw new Error("Invalid unsent change on this phone. Export it before doing anything else.");
        }
        keys.add(command.key);
    }
    const submitIndex = journal.pending.findIndex((command) => command.operation === "submit");
    if (submitIndex >= 0 && journal.pending.slice(submitIndex + 1).some((c) => CAPTURE.has(c.operation))) {
        throw new Error("A submission must be the last score change.");
    }
    return journal;
}

/** Queue a save, undo or submit of the current draft. */
export function queueCapture(journal, operation, confirmation = null) {
    if (!CAPTURE.has(operation)) throw new Error("Unknown operation.");
    if (isLocked(journal)) throw new Error("This result was already submitted.");
    if (journal.conflict) throw new Error("Resolve the conflict first.");
    if (journal.pending.length >= MAX_PENDING) throw new Error("Send or export the unsent changes first.");
    if (operation === "undo" && journal.pending.length) throw new Error("Send the unsent changes before undoing.");
    const next = clone(journal);
    const command = {
        key: newKey(),
        revision: next.base.revision + capturePending(next).length,
        operation,
        payload: clone(next.draft),
        signature: next.base.signature,
    };
    if (operation === "submit" && confirmation) command.confirmation = clone(confirmation);
    next.pending.push(command);
    next.dirty = false;
    next.updated_at = new Date().toISOString();
    return next;
}

/** Queue the full crossed-out list or match log (replaces an unsent one). */
export function queueSide(journal, operation) {
    if (!SIDE.has(operation)) throw new Error("Unknown operation.");
    if (isLocked(journal)) throw new Error("This result was already submitted.");
    const next = clone(journal);
    const payload = operation === "participation"
        ? { sheets: Object.fromEntries(Object.entries(next.crossed).map(([id, players]) => [String(id), players])) }
        : { events: next.log };
    next.pending = next.pending.filter((command) => command.operation !== operation || command.sent);
    if (next.pending.length >= MAX_PENDING) throw new Error("Send or export the unsent changes first.");
    next.pending.push({ key: newKey(), operation, payload });
    next.updated_at = new Date().toISOString();
    return next;
}

/** Commands to send now: everything pending, in order, without local flags. */
export function outgoing(journal) {
    return journal.pending.map(({ sent, ...command }) => command);
}

/** Apply a server acknowledgement for the commands that were sent. */
export function applyAck(journal, current, acknowledgedKeys, sentKeys) {
    if (!Array.isArray(acknowledgedKeys) || acknowledgedKeys.length !== sentKeys.length
        || sentKeys.some((key, index) => acknowledgedKeys[index] !== key)) {
        throw new Error("The server did not confirm every change. They stay on this phone.");
    }
    const acked = new Set(acknowledgedKeys);
    const next = clone(journal);
    next.pending = next.pending.filter((command) => !acked.has(command.key));
    next.base = { revision: current.revision, signature: current.signature };
    next.server = {
        result_state: current.result_state,
        submitted: current.submitted,
        closed: current.closed,
        device_id: current.device_id,
        this_device: current.this_device,
        referee_confirmation: current.referee_confirmation,
    };
    // Unsent capture commands were queued against the old revision.
    let revision = next.base.revision;
    for (const command of next.pending) {
        if (CAPTURE.has(command.operation)) command.revision = revision++;
    }
    if (!next.pending.length && !next.dirty) {
        next.draft = clone(current.payload);
        next.log = clone(current.match_log || next.log);
    }
    next.conflict = null;
    next.updated_at = new Date().toISOString();
    return next;
}

/** After taking the match over: queued changes now build on the server state. */
export function rebase(journal, current) {
    const next = clone(journal);
    next.base = { revision: current.revision, signature: current.signature };
    next.server = {
        ...next.server,
        result_state: current.result_state,
        submitted: current.submitted,
        closed: current.closed,
        device_id: current.device_id,
        this_device: current.this_device,
    };
    let revision = next.base.revision;
    for (const command of next.pending) {
        command.sent = false;
        if (CAPTURE.has(command.operation)) {
            command.revision = revision++;
            command.signature = current.signature;
        }
    }
    next.conflict = null;
    next.updated_at = new Date().toISOString();
    return next;
}

export function markConflict(journal, message, code = "conflict") {
    const next = clone(journal);
    next.conflict = { message, code, at: new Date().toISOString() };
    return next;
}

/** After the scorer kept the server version: drop local changes (exported first). */
export function resetToServer(journal, match) {
    const next = newJournal(match, journal.matchday_id);
    next.server.this_device = journal.server.this_device;
    return next;
}

/** Refresh a journal from a new pack, keeping anything not yet sent. */
export function refreshFromPack(journal, match) {
    if (journal.pending.length || journal.dirty) {
        const next = clone(journal);
        next.server.result_state = match.result_state;
        if (match.signature !== journal.base.signature && capturePending(journal).length) {
            next.conflict = next.conflict || {
                message: "The match changed on the server (time, court or result). Your scores stay on this phone.",
                code: "changed",
                at: new Date().toISOString(),
            };
        }
        return next;
    }
    const next = newJournal(match, journal.matchday_id);
    next.server.this_device = journal.server.this_device || next.server.this_device;
    return next;
}

/** One status per match for the list and the status bar. */
export function status(journal) {
    if (!journal) return "not_started";
    if (journal.conflict) return "conflict";
    if (journal.pending.some((c) => c.operation === "submit")) return "submit_waiting";
    if (journal.pending.length) return "waiting";
    if (journal.dirty) return "draft";
    if (journal.server.result_state === "approved") return "approved";
    if (journal.server.submitted || ["submitted", "verified"].includes(journal.server.result_state)) return "submitted";
    if (journal.server.result_state === "contested") return "contested";
    return journal.base.revision ? "saved" : "not_started";
}

/**
 * Unsent journals of the backend court app ("Run This Court") for this
 * database and user. Their commands can be sent through the phone API.
 */
export function legacyJournals(storage, database, userId) {
    const prefix = `sf-court:v1:${database}:${userId}:`;
    const found = [];
    for (let index = 0; index < storage.length; index++) {
        const name = storage.key(index);
        if (!name || !name.startsWith(prefix) || name === `${prefix}last`) continue;
        let record;
        try {
            record = JSON.parse(storage.getItem(name));
        } catch {
            continue;
        }
        if (!record || !Array.isArray(record.pending) || !record.pending.length) continue;
        const matchId = Number(name.slice(prefix.length).split(":")[2]);
        if (!Number.isInteger(matchId)) continue;
        found.push({ name, match_id: matchId, record });
    }
    return found;
}

/** Move backend-app commands into the phone journal (original keys kept). */
export function adoptLegacy(journal, legacy) {
    const next = clone(journal);
    const known = new Set(next.pending.map((command) => command.key));
    for (const command of legacy.record.pending) {
        if (known.has(command.key)) continue;
        if (!CAPTURE.has(command.operation)) continue;
        next.pending.push({
            key: command.key,
            revision: command.revision,
            operation: command.operation,
            payload: clone(command.payload),
            signature: command.signature,
        });
    }
    if (legacy.record.draft) next.draft = clone(legacy.record.draft);
    next.legacy_name = legacy.name;
    next.updated_at = new Date().toISOString();
    return next;
}
