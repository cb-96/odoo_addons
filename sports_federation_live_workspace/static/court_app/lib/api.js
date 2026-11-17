// Device API client. Every call sends the device token; the server re-checks
// the scorer's rights for each match.

export class NetworkError extends Error {}

export class ApiError extends Error {
    constructor(message, status, code) {
        super(message);
        this.status = status;
        this.code = code;
    }
}

export class Api {
    constructor(token, fetcher = (...args) => globalThis.fetch(...args)) {
        this.token = token;
        this.fetcher = fetcher;
    }

    async post(path, body = {}) {
        let response;
        try {
            response = await this.fetcher(path, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
                },
                body: JSON.stringify(body),
                credentials: "omit",
                cache: "no-store",
            });
        } catch (error) {
            throw new NetworkError(error?.message || "No connection.");
        }
        let data = null;
        try {
            data = await response.json();
        } catch {
            data = null;
        }
        if (!response.ok) {
            throw new ApiError(data?.error || `Server answered ${response.status}.`, response.status, data?.code || "error");
        }
        return data;
    }

    activate(code) { return this.post("/court/api/activate", { code }); }
    pack() { return this.post("/court/api/pack"); }
    sync(matchId, commands) { return this.post("/court/api/sync", { match_id: matchId, commands }); }
    claim(matchId) { return this.post("/court/api/claim", { match_id: matchId }); }
    forget() { return this.post("/court/api/forget"); }
}
