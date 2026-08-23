/** @odoo-module **/

const boards = document.querySelectorAll(".sf-live-board[data-status-url]");
for (const board of boards) {
    const refresh = async () => {
        try {
            const response = await fetch(board.dataset.statusUrl, {headers: {Accept: "application/json"}});
            if (!response.ok) return;
            const payload = await response.json();
            for (const match of payload.matches) {
                const card = board.querySelector(`[data-match-id="${match.id}"]`);
                if (!card) continue;
                card.dataset.status = match.status;
                const status = card.querySelector(".sf-match-status");
                if (status) status.textContent = match.status.replaceAll("_", " ");
            }
        } catch (_) {
            // The board remains fully usable with its server-rendered snapshot.
        }
    };
    window.setInterval(refresh, 45000);
}
for (const button of document.querySelectorAll(".sf-jump-now")) {
    button.addEventListener("click", () => document.querySelector(".sf-gameday-grid tbody")?.scrollIntoView({behavior: "smooth", block: "center"}));
}
const clock = document.querySelector("#sf-display-clock");
if (clock) {
    const tick = () => { clock.textContent = new Intl.DateTimeFormat(undefined, {hour: "2-digit", minute: "2-digit", second: "2-digit"}).format(new Date()); };
    tick(); window.setInterval(tick, 1000);
}
