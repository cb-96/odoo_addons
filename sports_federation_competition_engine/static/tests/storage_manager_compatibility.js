/**
 * Keep Odoo's unit-test RPC cache usable on plain HTTP test hosts.
 *
 * `navigator.storage` is exposed only in secure contexts by Chromium. The
 * Odoo test page is often served from a LAN IP over HTTP, so provide the
 * minimal StorageManager API used by RPCCache. Production pages should still
 * use HTTPS when persistent browser storage is required.
 */
const isOdooTestPage = ["/web/tests", "/web/tests/legacy"].includes(window.location.pathname);

if (isOdooTestPage && (!navigator.storage || typeof navigator.storage.estimate !== "function")) {
    Object.defineProperty(navigator, "storage", {
        configurable: true,
        value: {
            estimate: () => Promise.resolve({ quota: Number.MAX_SAFE_INTEGER, usage: 0 }),
        },
    });
}
