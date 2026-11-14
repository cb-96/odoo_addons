"""Browser check of the offline court app against a stand-in server.

Optional: needs Playwright for Python and a Chromium build.

    python ci/court_app_browser/run.py [--chromium /path/to/chrome] [--screenshots DIR]

It prepares a phone, scores sets with 2/1 points, crosses out players, records
a card, saves, goes offline, reloads the app without a network, sends the
queued change when back online, submits (head referee and PIN), and checks a
conflict, a revoked phone and a 320 px dark-mode layout.
"""

import argparse
import os
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fake_server as fs  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--chromium", default=os.environ.get("COURT_APP_CHROMIUM"))
parser.add_argument("--screenshots", default=tempfile.mkdtemp(prefix="court-app-"))
args = parser.parse_args()
SHOTS = Path(args.screenshots)
SHOTS.mkdir(parents=True, exist_ok=True)
LAUNCH = {
    "args": ["--no-sandbox"],
    **({"executable_path": args.chromium} if args.chromium else {}),
}
server = ThreadingHTTPServer(("127.0.0.1", 8765), fs.H)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = "http://localhost:8765"
SENT = "document.querySelector('header') && document.querySelector('header').innerText.includes('Everything sent')"
results = []
errors = []


def check(name, condition):
    results.append((name, bool(condition)))
    print(("PASS " if condition else "FAIL ") + name)


def ignore(message):
    return "status of 401" in message or "status of 409" in message


with sync_playwright() as p:
    browser = p.chromium.launch(**LAUNCH)
    ctx = browser.new_context(
        viewport={"width": 390, "height": 844},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
    )
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on(
        "console",
        lambda m: (
            errors.append(m.text) if m.type == "error" and not ignore(m.text) else None
        ),
    )

    # 1. Without a token: preparation screen.
    page.goto(BASE + "/court/app")
    page.wait_for_selector("text=Prepare this phone")
    check(
        "no token shows preparation screen",
        page.locator("text=My court duties").count() > 0,
    )
    page.screenshot(path=SHOTS / "01-enrol.png")

    # 2. Activation from the one-time code in the fragment.
    page.goto(BASE + "/court/app#code=abc")
    page.wait_for_selector("text=Game day 3")
    check("code removed from the address bar", "#code" not in page.url)
    check(
        "match listed",
        page.locator("text=Gent Gladiators – Antwerp Ballistics").count() == 1,
    )
    if not page.evaluate("!!navigator.serviceWorker.controller"):
        page.reload()
    page.wait_for_function("navigator.serviceWorker.controller !== null", timeout=15000)
    page.wait_for_selector("text=Game day 3")
    page.screenshot(path=SHOTS / "02-home.png")

    # 3. Score sets, cross out players, record a card, save online.
    page.click("text=Gent Gladiators – Antwerp Ballistics")
    page.wait_for_selector("text=Who plays this match")
    page.click("text=Add set")
    for _ in range(3):
        page.click("button[data-action=inc][data-side=home][data-index='0']")
    page.click("text=Add set")
    for _ in range(2):
        page.click("button[data-action=inc][data-side=home][data-index='1']")
        page.click("button[data-action=inc][data-side=away][data-index='1']")
    check(
        "drawn set shows Draw", page.locator(".set .chip", has_text="Draw").count() == 1
    )
    check(
        "totals use 2/1 points", page.locator(".totals").inner_text().strip() == "3 – 1"
    )
    page.uncheck("input[data-sheet='11'][data-player='14']")
    page.uncheck("input[data-sheet='11'][data-player='13']")
    check(
        "crossing out updates the count",
        "12 / max 12 playing" in page.locator("fieldset").first.inner_text(),
    )
    form = page.locator("form[data-action=add-event]")
    form.locator("select[name=type]").select_option("card_blue")
    form.locator("select[name=player_id]").select_option("3")
    form.locator("input[name=set]").fill("2")
    form.locator("button[type=submit]").click()
    page.wait_for_selector(".log li")
    page.click("button[data-action=save]")
    page.wait_for_function(SENT, timeout=10000)
    ops = [c["operation"] for c in fs.STATE["received"]]
    check(
        "save, participation and log reached the server",
        {"save", "participation", "log"} <= set(ops),
    )
    check(
        "server has 2/1 points score",
        fs.STATE["payload"]["home"] == 3 and fs.STATE["payload"]["away"] == 1,
    )
    check("server has crossed-out players", fs.STATE["crossed"].get("11") == [13, 14])
    check(
        "server has the blue card",
        fs.STATE["log"] and fs.STATE["log"][0]["type"] == "card_blue",
    )
    page.screenshot(path=SHOTS / "03-match-online.png", full_page=True)

    # 4. Offline: change, save, reload the page with no network.
    ctx.set_offline(True)
    page.wait_for_timeout(300)
    page.click("text=Add set")
    page.click("button[data-action=inc][data-side=away][data-index='2']")
    page.click("button[data-action=save]")
    page.wait_for_timeout(300)
    check("offline status shown", "Offline" in page.locator("header").inner_text())
    check("unsent change counted", "not sent" in page.locator("header").inner_text())
    before = len(fs.STATE["received"])
    page.reload()
    page.wait_for_selector("text=Game day 3", timeout=10000)
    check(
        "app opens after reload without network",
        page.locator("text=Gent Gladiators – Antwerp Ballistics").count() == 1,
    )
    check(
        "unsent change survived the reload",
        "1 change not sent" in page.locator("header").inner_text(),
    )
    page.screenshot(path=SHOTS / "04-offline-reload.png")
    check("nothing sent while offline", len(fs.STATE["received"]) == before)

    # 5. Back online: the queued change is sent.
    ctx.set_offline(False)
    page.evaluate("window.dispatchEvent(new Event('online'))")
    page.wait_for_function(SENT, timeout=10000)
    check(
        "queued change sent when back online",
        fs.STATE["revision"] == 2 and fs.STATE["payload"]["away"] == 3,
    )

    # 6. Submit as head referee.
    page.click("text=Gent Gladiators – Antwerp Ballistics")
    page.wait_for_selector("text=Submit to the tournament manager")
    page.check("input[name=self_confirm]")
    page.click("text=Submit result")
    page.wait_for_selector("text=waits for the tournament manager", timeout=10000)
    page.wait_for_function(SENT, timeout=10000)
    check(
        "submitted with head-referee confirmation",
        fs.STATE["submitted"] and fs.STATE["confirmation"] == {"method": "self"},
    )
    page.screenshot(path=SHOTS / "05-submitted.png", full_page=True)

    # 7. Revoked token: the warning is shown, data stays.
    fs.STATE["token"] = "other"
    page.click("text=← All matches")
    page.click("text=Refresh game day")
    page.wait_for_selector("text=no longer prepared", timeout=10000)
    check("revoked phone shows the warning", True)
    page.screenshot(path=SHOTS / "06-revoked.png")
    browser.close()

    # 8. Assistant referee with PIN, small dark screen, then a conflict.
    fs.STATE.update(
        {
            "token": "tok-123",
            "revision": 0,
            "submitted": False,
            "result_state": "draft",
            "source": "assistant_referee",
            "payload": {
                "home": 0,
                "away": 0,
                "periods": [],
                "outcome": "normal",
                "reason": "",
                "zero_confirmed": False,
            },
            "log": [],
            "confirmation": None,
        }
    )
    browser = p.chromium.launch(**LAUNCH)
    ctx = browser.new_context(
        viewport={"width": 320, "height": 640},
        is_mobile=True,
        has_touch=True,
        color_scheme="dark",
    )
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE + "/court/app#code=abc")
    page.wait_for_selector("text=Game day 3")
    page.click("text=Gent Gladiators – Antwerp Ballistics")
    page.wait_for_selector("text=Head referee (Eva Claeys)")
    page.click("text=Add set")
    page.click("button[data-action=inc][data-side=home][data-index='0']")
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    check("no horizontal overflow at 320 px", overflow <= 0)
    page.screenshot(path=SHOTS / "07-assistant-dark-320.png", full_page=True)
    page.fill("input[name=pin]", "4821")
    page.click("text=Submit result")
    page.wait_for_selector("text=waits for the tournament manager", timeout=10000)
    page.wait_for_function(SENT, timeout=10000)
    check(
        "PIN confirmation sent with the submission",
        fs.STATE["confirmation"] == {"method": "pin", "pin": "4821"},
    )
    stored = page.evaluate("""async () => {
        const db = await new Promise(r => { const q = indexedDB.open('sf-court'); q.onsuccess = () => r(q.result); });
        const all = await new Promise(r => { const q = db.transaction('journals').objectStore('journals').getAll(); q.onsuccess = () => r(q.result); });
        return JSON.stringify(all); }""")
    check("PIN not kept on the phone after sending", "4821" not in stored)
    fs.STATE.update(
        {
            "revision": 0,
            "submitted": False,
            "result_state": "draft",
            "force_conflict": True,
        }
    )
    page.click("text=← All matches")
    page.click("text=Refresh game day")
    page.wait_for_timeout(500)
    page.click("text=Gent Gladiators – Antwerp Ballistics")
    page.wait_for_selector("text=Add set")
    page.click("text=Add set")
    page.click("button[data-action=save]")
    page.wait_for_selector("text=Conflict:", timeout=10000)
    check(
        "conflict shows export and keep-server actions",
        page.locator("text=Keep the server version").count() == 1
        and page.locator("button[data-action=export]").count() >= 1,
    )
    check(
        "refused change stays on the phone",
        "not sent" in page.locator("header").inner_text(),
    )
    page.screenshot(path=SHOTS / "08-conflict.png", full_page=True)
    check("no page errors", not errors)
    if errors:
        print("\n".join(errors[:10]))
    browser.close()
server.shutdown()
print(f"{sum(ok for _, ok in results)}/{len(results)} passed · screenshots in {SHOTS}")
raise SystemExit(0 if all(ok for _, ok in results) else 1)
