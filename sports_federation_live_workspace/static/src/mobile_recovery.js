/** @odoo-module **/
export const copy = value => JSON.parse(JSON.stringify(value));

export function readJournal(raw) {
    if (!raw) return null;
    const record = JSON.parse(raw);
    if (!record || !record.draft || !Array.isArray(record.pending) || record.pending.length > 100) {
        throw new Error('Invalid device journal. Export the original evidence before recovery.');
    }
    const keys = new Set();
    for (const command of record.pending) {
        if (!command || typeof command.key !== 'string' || !command.key || keys.has(command.key)
            || !Number.isInteger(command.revision) || command.revision < 0
            || !['save', 'submit', 'undo'].includes(command.operation)
            || typeof command.signature !== 'string' || !command.payload) {
            throw new Error('Invalid command journal. No automatic replay is permitted.');
        }
        keys.add(command.key);
    }
    if (record.pending.some((command, index) => command.operation === 'submit' && index !== record.pending.length - 1)) {
        throw new Error('Submission must be the last queued command.');
    }
    return record;
}

export function durableWrite(storage, name, record, expectedRaw) {
    if (storage.getItem(name) !== expectedRaw) throw new Error('Another tab changed this device journal. Export your evidence and reload.');
    const raw = JSON.stringify(record);
    storage.setItem(name, raw);
    if (storage.getItem(name) !== raw) throw new Error('Device save could not be verified. Keep this screen open and export evidence.');
    return raw;
}

export function acknowledgedState(current, commands, acknowledged) {
    if (!current || !Array.isArray(acknowledged) || acknowledged.length !== commands.length
        || commands.some((command, index) => acknowledged[index] !== command.key)) {
        throw new Error('Server acknowledgement is incomplete. Retain the original command keys and retry.');
    }
    return {match: copy(current), draft: copy(current.payload), pending: [], dirty: false};
}

export function saveState(state) {
    if (state.storageFailed) return 'memory';
    if (state.pending?.some(command => command.operation === 'submit')) return 'submission_pending';
    if (state.pending?.length || state.dirty) return 'device';
    if (state.match?.result_state === 'approved') return 'approved';
    if (state.match?.result_state === 'verified') return 'verified';
    if (state.match?.result_state === 'contested') return 'contested';
    if (state.match?.submitted || state.match?.result_state === 'submitted') return 'submitted';
    return state.match ? 'synchronised' : 'unchecked';
}

export function nextMatch(queue, now = Date.now()) {
    const open = queue.filter(match => ['draft', 'corrected'].includes(match.result_state)
        && !['cancelled', 'postponed'].includes(match.operational_state));
    return open.find(match => Date.parse(match.start.replace(' ', 'T') + 'Z') <= now
        && Date.parse(match.end.replace(' ', 'T') + 'Z') >= now) || open[0] || null;
}

// Days after which a fully synchronised court journal is removed from this
// device. Such a journal only repeats what the server already holds.
export const CLEAN_JOURNAL_MAX_AGE_DAYS = 14;

/**
 * Remove old, fully synchronised court journals for one database and user.
 *
 * A journal is removed only when it parses, has no queued commands, has no
 * unsent edits and was last saved more than ``maxAgeDays`` ago. Journals that
 * cannot be read are kept: they may be the only evidence and must be exported
 * by a person. The ``last`` pointer and keys outside ``prefix`` are untouched.
 * Returns the removed keys.
 */
export function pruneCleanJournals(storage, prefix, now = Date.now(), maxAgeDays = CLEAN_JOURNAL_MAX_AGE_DAYS) {
    const removed = [];
    const cutoff = now - maxAgeDays * 24 * 60 * 60 * 1000;
    const keys = [];
    for (let index = 0; index < storage.length; index++) {
        const name = storage.key(index);
        if (name && name.startsWith(prefix) && name !== `${prefix}last`) keys.push(name);
    }
    for (const name of keys) {
        let record;
        try { record = readJournal(storage.getItem(name)); } catch { continue; }
        if (!record || record.dirty || record.pending.length) continue;
        const savedAt = Date.parse(record.saved_at || '');
        if (!Number.isFinite(savedAt) || savedAt >= cutoff) continue;
        storage.removeItem(name);
        removed.push(name);
    }
    return removed;
}
