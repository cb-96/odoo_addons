// One editor per match on this phone, also across tabs. Uses Web Locks when
// available and falls back to a BroadcastChannel handshake.

export class MatchLock {
    constructor(name = "sf-court-lock") {
        this.release = null;
        this.channel = null;
        this.owned = new Set();
        this.name = name;
        if (!globalThis.navigator?.locks && globalThis.BroadcastChannel) {
            this.channel = new BroadcastChannel(name);
            this.channel.onmessage = (event) => {
                const { type, match } = event.data || {};
                if (type === "ask" && this.owned.has(match)) this.channel.postMessage({ type: "taken", match });
            };
        }
    }

    async acquire(matchId) {
        await this.releaseAll();
        if (globalThis.navigator?.locks) {
            return new Promise((resolve) => {
                globalThis.navigator.locks.request(`${this.name}:${matchId}`, { ifAvailable: true }, async (lock) => {
                    if (!lock) { resolve(false); return; }
                    await new Promise((done) => { this.release = done; resolve(true); });
                }).catch(() => resolve(false));
            });
        }
        if (!this.channel) return true; // Single-tab browser: nothing to coordinate.
        const taken = await new Promise((resolve) => {
            const timer = setTimeout(() => { this.channel.removeEventListener("message", listen); resolve(false); }, 300);
            const listen = (event) => {
                if (event.data?.type === "taken" && event.data.match === matchId) {
                    clearTimeout(timer);
                    this.channel.removeEventListener("message", listen);
                    resolve(true);
                }
            };
            this.channel.addEventListener("message", listen);
            this.channel.postMessage({ type: "ask", match: matchId });
        });
        if (taken) return false;
        this.owned.add(matchId);
        return true;
    }

    async releaseAll() {
        this.release?.();
        this.release = null;
        this.owned.clear();
    }
}
