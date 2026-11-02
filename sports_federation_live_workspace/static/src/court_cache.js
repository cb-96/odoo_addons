/** @odoo-module **/
export function restoreCourtCache(server, cached) {
    const clone = value => JSON.parse(JSON.stringify(value));
    const match = clone(server);
    const pending = Array.isArray(cached?.pending) ? clone(cached.pending) : [];
    const dirty = Boolean(cached?.dirty);
    let draft = clone(server.payload);
    let conflict = server.signature !== server.draft_signature;
    if (dirty || pending.length) {
        if (cached?.draft) draft = clone(cached.draft);
        else conflict = true;
        if (cached?.base) {
            match.revision = cached.base.revision;
            match.signature = cached.base.signature;
            // Pending commands carry immutable receipts; let server replay decide.
            if (!pending.length) conflict ||= cached.base.revision !== server.revision
                || cached.base.signature !== server.signature;
        } else conflict = true;
    }
    return {match, draft, pending, dirty, conflict};
}
