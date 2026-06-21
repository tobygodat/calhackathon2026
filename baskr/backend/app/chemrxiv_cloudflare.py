"""ChemRxiv Cloudflare-bypass fetcher — OPTIONAL / PURGEABLE add-on.

WHY THIS EXISTS
---------------
ChemRxiv's public API (https://chemrxiv.org/engage/chemrxiv/public-api/v1) is now
fronted by Cloudflare's *active* JS "managed challenge". Plain HTTP clients cannot
pass it — verified during diagnosis:

* ``requests`` with no/blank User-Agent  -> 403
* ``requests`` with a browser User-Agent -> "Just a moment..." JS challenge
* ``curl_cffi`` Chrome TLS impersonation -> still 403 + JS challenge

Only a real browser that executes the challenge JS can earn the ``cf_clearance``
cookie. This module drives a headless Chromium (via Playwright) to do that, then
issues the API call *from inside the browser page* so it carries the clearance
cookie.

WARNING - reliability caveat: Cloudflare escalates to an IP-level block when it sees
repeated automated hits. During testing, hammering the endpoint got this machine's
IP soft-blocked (all connections dropped). Keep call frequency LOW (the heartbeat
runs once per ~10 min, which is fine) and never poll it tightly.

PURGE INSTRUCTIONS (to remove the Cloudflare bypass entirely)
-------------------------------------------------------------
1. Delete this file (``app/chemrxiv_cloudflare.py``).
2. Nothing else is required: ``app/connections.py`` imports this module inside a
   try/except and falls back to the plain-HTTP ChemRxiv ping automatically.
3. Optionally: ``pip uninstall playwright curl_cffi``.

DEPENDENCIES
------------
* ``playwright`` (pip) + a Chrome/Chromium build. This module prefers the
  system-installed Chrome (``channel="chrome"``); if Playwright's own browser is
  installed (``playwright install chromium``) it will fall back to that.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

log = logging.getLogger("baskr.chemrxiv_cf")

HOME_URL = "https://chemrxiv.org/"
API_BASE = "https://chemrxiv.org/engage/chemrxiv/public-api/v1"

# Total wall-clock budget for one browser-backed fetch (launch + challenge + call).
DEFAULT_TIMEOUT_S = 45.0

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def available() -> bool:
    """True if Playwright is importable (the bypass *can* be attempted)."""
    try:
        import playwright  # noqa: F401,PLC0415

        return True
    except Exception:  # noqa: BLE001
        return False


def _launch(p: Any):
    """Launch Chromium, preferring system Chrome, then Playwright's own build."""
    # System Chrome is least likely to be flagged as automation by Cloudflare.
    try:
        return p.chromium.launch(channel="chrome", headless=True)
    except Exception as exc:  # noqa: BLE001
        log.debug("system Chrome launch failed (%s); trying bundled chromium", exc)
        return p.chromium.launch(headless=True)


def fetch_json(path: str, params: dict | None = None,
               timeout_s: float = DEFAULT_TIMEOUT_S) -> dict:
    """Fetch ``API_BASE + path`` through a real browser, returning parsed JSON.

    Raises on any failure (challenge not cleared, non-2xx, non-JSON, timeout) so
    callers can treat it like any other failed probe/fetch.
    """
    from urllib.parse import urlencode  # noqa: PLC0415

    from playwright.sync_api import sync_playwright  # noqa: PLC0415

    url = f"{API_BASE}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"

    deadline = time.monotonic() + timeout_s
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            ctx = browser.new_context(user_agent=_UA)
            page = ctx.new_page()
            # Solve the challenge on the HTML homepage (the JS needs a real page).
            page.goto(HOME_URL, wait_until="domcontentloaded",
                      timeout=int(max(1.0, deadline - time.monotonic()) * 1000))
            while time.monotonic() < deadline:
                title = (page.title() or "").lower()
                if title and "just a moment" not in title:
                    break
                time.sleep(1.0)
            # Now call the API from inside the cleared page (carries cf_clearance).
            result = page.evaluate(
                """async (u) => {
                    const r = await fetch(u, {headers: {'Accept': 'application/json'}});
                    return {status: r.status, body: await r.text()};
                }""",
                url,
            )
        finally:
            browser.close()

    status = result.get("status")
    body = result.get("body", "")
    if status != 200:
        raise RuntimeError(f"chemrxiv API returned HTTP {status}")
    if "just a moment" in body[:512].lower():
        raise RuntimeError("blocked by Cloudflare challenge (clearance not obtained)")
    return json.loads(body)


def ping(timeout_s: float = DEFAULT_TIMEOUT_S) -> bool:
    """Lightweight reachability check used by the heartbeat. Never raises."""
    try:
        data = fetch_json("/items", params={"limit": 1}, timeout_s=timeout_s)
        return isinstance(data, dict) and "itemHits" in data
    except Exception as exc:  # noqa: BLE001
        log.info("chemrxiv cloudflare ping failed: %s", exc)
        return False


if __name__ == "__main__":  # manual smoke test: python -m app.chemrxiv_cloudflare
    logging.basicConfig(level=logging.INFO)
    print("available:", available())
    print("ping:", ping())
