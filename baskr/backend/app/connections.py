"""Source connection registry + staggered heartbeat scheduler.

New stable-connection model
---------------------------
A source connection is considered **stable** when we have made *some sort of
contact* with it within the last ``STABLE_WINDOW_S`` seconds (30 minutes). Contact
is recorded two ways:

* a lightweight **heartbeat ping** the scheduler fires at every source on a fixed
  ``HEARTBEAT_INTERVAL_S`` cadence (10 minutes), and
* any real data fetch that actually reached the source (the producer / pipeline
  search call ``record_contact`` when a source returns rows).

Because the stable window (30 min) is three heartbeat intervals (10 min) wide, a
source stays "stable" as long as it answers roughly one in three pings — a single
transient failure never flips it red.

Staggering
----------
The 10-minute pings are **not** fired all at once. A single dispatcher thread wakes
every ``HEARTBEAT_INTERVAL_S / n_sources`` seconds and pings the *next* source in a
round-robin, so each source is contacted once per interval but the individual
requests are spread evenly across the window (one source every ~100 s for 6
sources). This avoids a thundering-herd burst against the upstream APIs.

Degraded-safe
-------------
Last-contact timestamps are mirrored to a Redis hash (``baskr:source_contact``) so
they survive a restart and are shared across replicas, but everything degrades to a
process-local dict when Redis is unreachable — no probe and no accessor here ever
raises.
"""

from __future__ import annotations

import datetime
import logging
import threading
import time
from typing import Any, Callable

from .config import SETTINGS, Settings

log = logging.getLogger("baskr.connections")

# How recently we must have contacted a source for it to count as "stable"
# (default; individual sources may override via STABLE_WINDOW_OVERRIDES_S).
STABLE_WINDOW_S = 30 * 60  # 30 minutes
# How often the scheduler contacts each individual source (default; overridable
# per-source via HEARTBEAT_INTERVAL_OVERRIDES_S).
HEARTBEAT_INTERVAL_S = 10 * 60  # 10 minutes

# Per-source overrides. PubMed's anonymous NCBI endpoint is rate-limited, so a
# per-/status-poll probe makes it flap constantly. Instead we ping it on a short
# few-minute cadence and treat it as stable as long as *some* contact landed in
# the last few minutes — no reading-every-second required, but at least one every
# few minutes keeps it green. A 6-minute window over a 2-minute ping tolerates two
# consecutive missed pings before it flips down.
HEARTBEAT_INTERVAL_OVERRIDES_S: dict[str, float] = {
    "pubmed": 2 * 60,    # ping PubMed every ~2 minutes
    "chemrxiv": 5 * 60,  # ChemRxiv is slow + flaky — probe gently, every ~5 minutes
}
STABLE_WINDOW_OVERRIDES_S: dict[str, float] = {
    "pubmed": 6 * 60,  # stable if contacted within the last ~6 minutes
}

# Best-effort ("optional") sources: their public API is unreliable — ChemRxiv sits
# behind Cloudflare bot protection and answers slowly or not at all. We keep them
# *wired and ready* rather than letting an outage drag the whole system to
# "degraded". When an optional source isn't currently stable it reports state
# "ready" (standby) instead of "down": the integration is live and will start
# flowing the moment the source answers a heartbeat or a real fetch.
OPTIONAL_SOURCES: frozenset[str] = frozenset({"chemrxiv"})

# Per-source heartbeat request timeout. A value may be a float (total) or a
# ``(connect, read)`` tuple — the latter bounds total wall time so the scheduler
# thread never blocks for long on a slow/blocked source. ChemRxiv gets a generous
# read budget (it can answer slowly when it answers at all) but a tight connect
# budget so a Cloudflare-blocked attempt fails fast rather than hanging ~40 s.
DEFAULT_PING_TIMEOUT_S: float = 8.0
PING_TIMEOUT_OVERRIDES_S: dict[str, float | tuple[float, float]] = {
    "chemrxiv": (5.0, 15.0),
}


def stable_window_s(source: str) -> float:
    """Seconds-since-contact within which ``source`` counts as stable."""
    return STABLE_WINDOW_OVERRIDES_S.get(source, STABLE_WINDOW_S)


def heartbeat_interval_s(source: str) -> float:
    """How often the scheduler should ping ``source``."""
    return HEARTBEAT_INTERVAL_OVERRIDES_S.get(source, HEARTBEAT_INTERVAL_S)


def ping_timeout_s(source: str) -> float | tuple[float, float]:
    """HTTP timeout to use for ``source``'s heartbeat ping (float or tuple)."""
    return PING_TIMEOUT_OVERRIDES_S.get(source, DEFAULT_PING_TIMEOUT_S)


def is_optional(source: str) -> bool:
    """True if ``source`` is best-effort (reports 'ready' standby instead of down)."""
    return source in OPTIONAL_SOURCES

# Redis hash storing ``{source: iso_ts}`` of the last successful contact.
CONTACT_HASH_KEY = "baskr:source_contact"

# The data sources we keep a stable connection to. Order here defines the
# round-robin stagger order.
SOURCES: tuple[str, ...] = (
    "pubmed",
    "arxiv",
    "biorxiv",
    "openalex",
    "chemrxiv",
    "medrxiv",
)

# ---------------------------------------------------------------------------
# Last-contact store (process-local mirror of the Redis hash)
# ---------------------------------------------------------------------------

_lock = threading.Lock()
_last_contact: dict[str, float] = {}  # source -> epoch seconds

# Scheduler state.
_thread: threading.Thread | None = None
_stop_event = threading.Event()
_scheduler_last_tick: str | None = None


def _now_epoch() -> float:
    return datetime.datetime.now(datetime.timezone.utc).timestamp()


def _iso(epoch: float) -> str:
    return (
        datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _iso_to_epoch(value: str) -> float | None:
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Public API — recording + querying contact
# ---------------------------------------------------------------------------

def record_contact(source: str, settings: Settings = SETTINGS,
                   epoch: float | None = None) -> None:
    """Record that we just made contact with ``source`` (heartbeat or real fetch).

    Updates the in-process mirror immediately and best-effort mirrors to the Redis
    hash so the timestamp survives restarts. Never raises.
    """
    ts = epoch if epoch is not None else _now_epoch()
    with _lock:
        _last_contact[source] = ts
    try:
        from .redis_client import get_client  # noqa: PLC0415

        get_client(settings).hset(CONTACT_HASH_KEY, source, _iso(ts))
    except Exception as exc:  # noqa: BLE001  (contact tracking must never break a fetch)
        log.debug("record_contact: Redis mirror failed for %s (%s)", source, exc)


def _load_contact(source: str, settings: Settings = SETTINGS) -> float | None:
    """Most recent contact epoch for ``source`` (memory first, then Redis)."""
    with _lock:
        local = _last_contact.get(source)
    if local is not None:
        return local
    try:
        from .redis_client import get_client  # noqa: PLC0415

        raw = get_client(settings).hget(CONTACT_HASH_KEY, source)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode()
        epoch = _iso_to_epoch(raw)
        if epoch is not None:
            with _lock:
                _last_contact[source] = epoch
        return epoch
    except Exception:  # noqa: BLE001
        return None


def last_contact(source: str, settings: Settings = SETTINGS) -> str | None:
    """ISO-8601 Z timestamp of the last contact with ``source``, or None."""
    epoch = _load_contact(source, settings)
    return _iso(epoch) if epoch is not None else None


def age_seconds(source: str, settings: Settings = SETTINGS,
                now: float | None = None) -> float | None:
    """Whole seconds since the last contact with ``source`` (None if never)."""
    epoch = _load_contact(source, settings)
    if epoch is None:
        return None
    if now is None:
        now = _now_epoch()
    return max(0.0, now - epoch)


def is_stable(source: str, settings: Settings = SETTINGS,
              now: float | None = None) -> bool:
    """True iff we contacted ``source`` within its stable window (see ``stable_window_s``)."""
    age = age_seconds(source, settings, now=now)
    return age is not None and age <= stable_window_s(source)


def source_state(source: str, settings: Settings = SETTINGS,
                 now: float | None = None) -> str:
    """Coarse connection state for ``source``.

    * ``"stable"`` — contacted within its stable window (actively usable).
    * ``"ready"``  — an optional/best-effort source that isn't currently stable but
      is wired and will activate the moment it answers (standby, not a failure).
    * ``"stale"``  — a required source we *did* reach before but not recently.
    * ``"down"``   — a required source we've never reached.
    """
    if is_stable(source, settings, now=now):
        return "stable"
    if is_optional(source):
        return "ready"
    if _load_contact(source, settings) is not None:
        return "stale"
    return "down"


def source_status(source: str, settings: Settings = SETTINGS) -> dict[str, Any]:
    """A ``/status``-shaped connection entry for ``source``.

    Optional sources never report ``ok: false`` just for being idle — they surface
    as ``status: "ready"`` (standby) so a flaky upstream doesn't mark the whole
    system unhealthy, while still clearly showing they are not live *right now*.
    """
    age = age_seconds(source, settings)
    state = source_state(source, settings)
    if state == "stable":
        return {"ok": True, "detail": f"contact {(age or 0) / 60:.1f} min ago"}
    if state == "ready":
        detail = (
            "standby — wired, no contact yet" if age is None
            else f"standby — last contact {int(age)}s ago"
        )
        return {"ok": True, "status": "ready", "detail": detail}
    if state == "stale":
        return {
            "ok": False, "status": "down",
            "detail": f"last contact {int(age or 0)}s ago "
                      f"(stale > {int(stable_window_s(source))}s)",
        }
    return {"ok": False, "status": "down", "detail": "no contact yet"}


def connection_report(settings: Settings = SETTINGS) -> dict[str, dict[str, Any]]:
    """Per-source stability summary for ``/status`` and the dashboard.

    ``{source: {"stable", "state", "optional", "last_contact", "age_seconds"}}``
    """
    now = _now_epoch()
    report: dict[str, dict[str, Any]] = {}
    for source in SOURCES:
        age = age_seconds(source, settings, now=now)
        report[source] = {
            "stable": age is not None and age <= stable_window_s(source),
            "state": source_state(source, settings, now=now),
            "optional": is_optional(source),
            "last_contact": last_contact(source, settings),
            "age_seconds": int(age) if age is not None else None,
        }
    return report


# ---------------------------------------------------------------------------
# Heartbeat pings (lightweight reachability checks, one per source)
# ---------------------------------------------------------------------------

def _ping_pubmed(timeout: float = DEFAULT_PING_TIMEOUT_S) -> None:
    import requests  # noqa: PLC0415
    requests.get(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi",
        params={"retmode": "json"}, timeout=timeout,
    ).raise_for_status()


def _ping_arxiv(timeout: float = DEFAULT_PING_TIMEOUT_S) -> None:
    import requests  # noqa: PLC0415
    requests.get(
        "http://export.arxiv.org/api/query",
        params={"search_query": "all:microbiome", "max_results": 1}, timeout=timeout,
    ).raise_for_status()


def _ping_biorxiv(timeout: float = DEFAULT_PING_TIMEOUT_S) -> None:
    import requests  # noqa: PLC0415
    requests.get("https://api.biorxiv.org/details/biorxiv/2024-01-01/2024-01-02/0",
                 timeout=timeout).raise_for_status()


def _ping_medrxiv(timeout: float = DEFAULT_PING_TIMEOUT_S) -> None:
    import requests  # noqa: PLC0415
    requests.get("https://api.medrxiv.org/details/medrxiv/2024-01-01/2024-01-02/0",
                 timeout=timeout).raise_for_status()


def _ping_openalex(timeout: float = DEFAULT_PING_TIMEOUT_S) -> None:
    import requests  # noqa: PLC0415
    requests.get("https://api.openalex.org/works",
                 params={"per-page": 1, "mailto": "baskr@example.com"},
                 timeout=timeout).raise_for_status()


def _ping_chemrxiv(timeout: float = DEFAULT_PING_TIMEOUT_S) -> None:
    import requests  # noqa: PLC0415
    # ChemRxiv's public API sits behind Cloudflare bot protection (403s blank
    # User-Agents, serves a JS "Just a moment..." interstitial to others) and is slow
    # to answer (~15-20 s), so it gets a longer timeout (see PING_TIMEOUT_OVERRIDES_S).
    # Send a browser-like UA so we pass when Cloudflare isn't actively challenging this
    # IP, and treat a challenge page as an explicit failure (rather than a misleading
    # 200) so the source's readiness is reported honestly.
    resp = requests.get(
        "https://chemrxiv.org/engage/chemrxiv/public-api/v1/items",
        params={"limit": 1},
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    if "just a moment" in resp.text[:512].lower():
        raise RuntimeError("blocked by Cloudflare challenge")


# Map each source to its heartbeat ping (each accepts a timeout). A source absent
# here cannot be pinged and can only become stable via a real data fetch calling
# ``record_contact``.
PINGS: dict[str, Callable[..., None]] = {
    "pubmed": _ping_pubmed,
    "arxiv": _ping_arxiv,
    "biorxiv": _ping_biorxiv,
    "medrxiv": _ping_medrxiv,
    "openalex": _ping_openalex,
    "chemrxiv": _ping_chemrxiv,
}


def ping_source(source: str, settings: Settings = SETTINGS) -> bool:
    """Fire one heartbeat ping at ``source``; record contact on success.

    Uses the source's per-source timeout (``ping_timeout_s``). Returns True if the
    ping reached the source. Never raises.
    """
    ping = PINGS.get(source)
    if ping is None:
        return False
    try:
        ping(ping_timeout_s(source))
        record_contact(source, settings)
        log.debug("heartbeat: %s OK", source)
        return True
    except Exception as exc:  # noqa: BLE001
        level = log.debug if is_optional(source) else log.info
        level("heartbeat: %s unreachable (%s)", source, exc)
        return False


# ---------------------------------------------------------------------------
# Staggered scheduler
# ---------------------------------------------------------------------------

def _run_scheduler(settings: Settings) -> None:
    """Ping each source on its own cadence (see ``heartbeat_interval_s``).

    Every source keeps an independent next-due time, so a rate-limited source like
    PubMed can be pinged every couple of minutes while the rest stay on the slow
    default. Initial pings are staggered across one default interval so startup
    isn't a thundering-herd burst.
    """
    global _scheduler_last_tick
    sources = list(PINGS.keys())
    n = max(1, len(sources))
    base = time.monotonic()
    stagger = HEARTBEAT_INTERVAL_S / n  # spread the first pings out
    next_due = {s: base + i * stagger for i, s in enumerate(sources)}
    log.info("Heartbeat scheduler: %d sources, per-source cadence "
             "(default %ds, overrides=%s)",
             n, HEARTBEAT_INTERVAL_S, HEARTBEAT_INTERVAL_OVERRIDES_S)

    while not _stop_event.is_set():
        now = time.monotonic()
        for source in sources:
            if now >= next_due[source]:
                ping_source(source, settings)
                next_due[source] = time.monotonic() + heartbeat_interval_s(source)
                _scheduler_last_tick = _iso(_now_epoch())
        # Sleep until the soonest next-due, but wake at least every few seconds so
        # stop() stays responsive and timing doesn't drift.
        sleep_for = min(next_due.values()) - time.monotonic()
        _stop_event.wait(max(0.5, min(sleep_for, 5.0)))


def start_heartbeats(settings: Settings = SETTINGS) -> None:
    """Start the staggered heartbeat scheduler thread. Idempotent."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(
        target=_run_scheduler, args=(settings,), daemon=True, name="baskr-heartbeats"
    )
    _thread.start()
    log.info("Heartbeat scheduler started (thread %s)", _thread.name)


def stop_heartbeats() -> None:
    """Stop the heartbeat scheduler thread."""
    _stop_event.set()
    if _thread is not None:
        _thread.join(timeout=5)
    log.info("Heartbeat scheduler stopped")


def scheduler_last_tick() -> str | None:
    """ISO timestamp of the scheduler's most recent ping, or None."""
    return _scheduler_last_tick


def reset_state() -> None:
    """Clear the in-process contact mirror (test isolation)."""
    with _lock:
        _last_contact.clear()
