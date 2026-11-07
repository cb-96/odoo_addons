// IndexedDB storage for the offline court app.
//
// meta:     device token, app state (key/value)
// pack:     the current game-day pack (key "current")
// journals: one journal per match (keyPath match_id)
//
// Writes are awaited until the transaction completes, so a change is only
// reported as "saved on this phone" after IndexedDB confirmed it.

const DB_NAME = "sf-court";
const DB_VERSION = 1;

function promisify(request) {
    return new Promise((resolve, reject) => {
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

export class Store {
    constructor(db) {
        this.db = db;
    }

    static async open(factory = globalThis.indexedDB) {
        if (!factory) throw new Error("This browser cannot store data offline.");
        const request = factory.open(DB_NAME, DB_VERSION);
        request.onupgradeneeded = () => {
            const db = request.result;
            if (!db.objectStoreNames.contains("meta")) db.createObjectStore("meta");
            if (!db.objectStoreNames.contains("pack")) db.createObjectStore("pack");
            if (!db.objectStoreNames.contains("journals")) db.createObjectStore("journals", { keyPath: "match_id" });
        };
        return new Store(await promisify(request));
    }

    async _tx(storeName, mode, work) {
        const tx = this.db.transaction(storeName, mode);
        const done = new Promise((resolve, reject) => {
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
            tx.onabort = () => reject(tx.error || new Error("Storage write aborted."));
        });
        const result = await work(tx.objectStore(storeName));
        await done;
        return result;
    }

    get(storeName, key) {
        return this._tx(storeName, "readonly", (store) => promisify(store.get(key)));
    }

    put(storeName, value, key) {
        return this._tx(storeName, "readwrite", (store) =>
            promisify(key === undefined ? store.put(value) : store.put(value, key)));
    }

    delete(storeName, key) {
        return this._tx(storeName, "readwrite", (store) => promisify(store.delete(key)));
    }

    all(storeName) {
        return this._tx(storeName, "readonly", (store) => promisify(store.getAll()));
    }

    clear(storeName) {
        return this._tx(storeName, "readwrite", (store) => promisify(store.clear()));
    }

    // Convenience
    meta(key) { return this.get("meta", key); }
    setMeta(key, value) { return this.put("meta", value, key); }
    pack() { return this.get("pack", "current"); }
    setPack(pack) { return this.put("pack", pack, "current"); }
    journal(matchId) { return this.get("journals", matchId); }
    saveJournal(journal) { return this.put("journals", journal); }
    journals() { return this.all("journals"); }

    async wipe() {
        await this.clear("journals");
        await this.clear("pack");
        await this.clear("meta");
    }
}

/** Ask the browser to keep this data when space runs low. */
export async function requestPersistence(storage = globalThis.navigator?.storage) {
    if (!storage?.persist) return false;
    try {
        if (await storage.persisted()) return true;
        return await storage.persist();
    } catch {
        return false;
    }
}
