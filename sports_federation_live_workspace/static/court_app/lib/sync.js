// Sending queued changes and refreshing the game-day pack.
//
// The server decides: an acknowledged change is removed from the phone, a
// refused change turns the match into a conflict (never merged), and a
// network failure leaves everything queued for the next attempt.

import { ApiError, NetworkError } from "./api.js";
import { applyAck, markConflict, newJournal, outgoing, refreshFromPack } from "./journal.js";

export async function syncJournal(store, api, journal) {
    if (!journal.pending.length || journal.conflict) return { journal, sent: 0 };
    const commands = outgoing(journal);
    const sentKeys = commands.map((command) => command.key);
    const marked = { ...journal, pending: journal.pending.map((command) => ({ ...command, sent: true })) };
    await store.saveJournal(marked);
    let result;
    try {
        result = await api.sync(journal.match_id, commands);
    } catch (error) {
        if (error instanceof NetworkError) return { journal: marked, sent: 0, offline: true };
        if (error instanceof ApiError && error.status === 401) {
            return { journal: marked, sent: 0, unauthorized: error.message };
        }
        if (error instanceof ApiError && error.status === 429) return { journal: marked, sent: 0, offline: true };
        const conflicted = markConflict(marked, error.message, error.code || "conflict");
        await store.saveJournal(conflicted);
        return { journal: conflicted, sent: 0, conflict: error.message };
    }
    const latest = (await store.journal(journal.match_id)) || marked;
    const next = applyAck(latest, result.current, result.acknowledged_keys, sentKeys);
    await store.saveJournal(next);
    if (next.legacy_name && !next.pending.length) {
        try { globalThis.localStorage?.removeItem(next.legacy_name); } catch { /* Kept: harmless. */ }
    }
    return { journal: next, sent: sentKeys.length };
}

/** Send every match with queued changes. Stops at the first network failure. */
export async function syncAll(store, api) {
    const summary = { sent: 0, conflicts: 0, offline: false, unauthorized: null };
    for (const journal of await store.journals()) {
        if (!journal.pending.length || journal.conflict) continue;
        const result = await syncJournal(store, api, journal);
        summary.sent += result.sent;
        if (result.conflict) summary.conflicts += 1;
        if (result.offline) { summary.offline = true; break; }
        if (result.unauthorized) { summary.unauthorized = result.unauthorized; break; }
    }
    return summary;
}

/**
 * Download the pack and merge it into the journals. Returns the changes the
 * scorer should see: matches added, removed or moved since the last pack.
 */
export async function refreshPack(store, api) {
    const previous = await store.pack();
    const pack = await api.pack();
    const changes = [];
    const before = new Map((previous?.matches || []).map((match) => [match.id, match]));
    const now = new Map(pack.matches.map((match) => [match.id, match]));
    for (const match of pack.matches) {
        const old = before.get(match.id);
        if (!old && previous) changes.push({ type: "added", match: match.name });
        else if (old && (old.start !== match.start || old.court !== match.court)) {
            changes.push({ type: "moved", match: match.name, start: match.start, court: match.court });
        }
        const journal = await store.journal(match.id);
        await store.saveJournal(journal ? refreshFromPack(journal, match) : newJournal(match, pack.matchday.id));
    }
    for (const journal of await store.journals()) {
        if (now.has(journal.match_id)) continue;
        const name = before.get(journal.match_id)?.name || `#${journal.match_id}`;
        changes.push({ type: "removed", match: name });
        if (journal.pending.length || journal.dirty) {
            await store.saveJournal(markConflict(journal,
                "This match is no longer on your list (moved, cancelled or you are no longer a scorer). Export your scores.",
                "removed"));
        } else {
            await store.delete("journals", journal.match_id);
        }
    }
    await store.setPack(pack);
    await store.setMeta("last_pack_at", new Date().toISOString());
    return { pack, changes, changed: previous?.pack_hash !== pack.pack_hash };
}
