"""Monitoring CSV logs for the dev-ui.

Two append-only CSV logs live under ``baskr/data``:

* ``new_papers_seen.csv``  — one row per *distinct* paper ever returned by
  ``/pipeline/search`` (header ``first_seen_at,source,source_id,title``). The
  distinct count survives restarts because the keys are reloaded from the CSV
  on import.
* ``service_status_log.csv`` — one row each time a monitored connection (or the
  backend process itself) flips between up/down (header
  ``connection,changed_at,transition,seconds_since_previous``). ``transition`` is
  ``"on"`` (now reachable) or ``"off"``; ``seconds_since_previous`` is how long
  the connection held its *previous* status before this flip.

All writes go through a module-level lock so concurrent ``/status`` polls and a
pipeline search can append safely. The CSV paths are module-level constants so
tests can repoint them at a tmp dir.
"""

from __future__ import annotations

import csv
import threading
from datetime import datetime, timezone
from pathlib import Path

# app/ -> backend/ -> baskr/ -> data/
_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

NEW_PAPERS_CSV = _DATA_DIR / "new_papers_seen.csv"
STATUS_LOG_CSV = _DATA_DIR / "service_status_log.csv"

_NEW_PAPERS_HEADER = ["first_seen_at", "source", "source_id", "title"]
_STATUS_LOG_HEADER = ["connection", "changed_at", "transition", "seconds_since_previous"]

_lock = threading.Lock()

# Distinct-paper identity. ``_seen_sids`` (source:source_id) is the persisted
# identity that drives the count and survives restarts; ``_seen_uids`` adds extra
# runtime dedup for papers that carry a cross-source uid.
_seen_sids: set[str] = set()
_seen_uids: set[str] = set()

# Epoch timestamps of every distinct paper first-seen (for time-based metrics),
# and the ISO string of the most recent one.
_seen_times: list[float] = []
_last_new_paper_iso: str | None = None

# Per-connection last-observed status and the epoch at which it last changed.
_last_ok: dict[str, bool] = {}
_last_change_at: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _now() -> tuple[float, str]:
    """Return ``(epoch_seconds, iso_z_string)`` for one consistent instant."""
    dt = datetime.now(timezone.utc)
    iso = dt.isoformat(timespec="seconds").replace("+00:00", "Z")
    return dt.timestamp(), iso


def _iso_to_epoch(value: str) -> float | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# CSV helpers (callers must hold ``_lock``)
# ---------------------------------------------------------------------------

def _append_rows(path: Path, header: list[str], rows: list[list]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not (path.exists() and path.stat().st_size > 0)
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(header)
        writer.writerows(rows)


def _sid(paper: dict) -> str:
    return f"{paper.get('source', '')}:{paper.get('source_id', '')}"


def _load_seen_keys() -> None:
    """Populate the in-memory paper sets/times from ``NEW_PAPERS_CSV`` (import-time)."""
    global _last_new_paper_iso
    if not NEW_PAPERS_CSV.exists():
        return
    try:
        with NEW_PAPERS_CSV.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                sid = f"{row.get('source', '')}:{row.get('source_id', '')}"
                if sid != ":":
                    _seen_sids.add(sid)
                seen_at = row.get("first_seen_at", "")
                epoch = _iso_to_epoch(seen_at)
                if epoch is not None:
                    _seen_times.append(epoch)
                    _last_new_paper_iso = seen_at  # rows are chronological
    except Exception:
        pass


def _last_backend_row() -> tuple[float | None, str | None]:
    """``(epoch, transition)`` of the most recent ``backend`` row, or ``(None, None)``."""
    if not STATUS_LOG_CSV.exists():
        return None, None
    last_epoch: float | None = None
    last_trans: str | None = None
    try:
        with STATUS_LOG_CSV.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("connection") == "backend":
                    epoch = _iso_to_epoch(row.get("changed_at", ""))
                    if epoch is not None:
                        last_epoch = epoch
                        last_trans = row.get("transition")
    except Exception:
        return None, None
    return last_epoch, last_trans


# ---------------------------------------------------------------------------
# Public API — new papers
# ---------------------------------------------------------------------------

def record_papers(papers: list[dict]) -> int:
    """Append a row for each *new* paper in ``papers``; return the running total.

    Dedup key is the paper's ``uid`` (when present) plus its ``source:source_id``,
    so a paper is never counted twice within or across runs.
    """
    global _last_new_paper_iso
    with _lock:
        new_rows: list[list] = []
        now_epoch, now_iso = _now()
        for p in papers:
            sid = _sid(p)
            uid = p.get("uid") or ""
            if sid in _seen_sids or (uid and uid in _seen_uids):
                continue
            _seen_sids.add(sid)
            if uid:
                _seen_uids.add(uid)
            _seen_times.append(now_epoch)
            _last_new_paper_iso = now_iso
            title = (p.get("title") or "").replace("\r", " ").replace("\n", " ").strip()
            new_rows.append([now_iso, p.get("source", ""), p.get("source_id", ""), title])
        _append_rows(NEW_PAPERS_CSV, _NEW_PAPERS_HEADER, new_rows)
        return len(_seen_sids)


def seen_count() -> int:
    """Distinct papers seen across all ``/pipeline/search`` calls."""
    return len(_seen_sids)


def last_new_paper_at() -> str | None:
    """ISO-8601 Z timestamp when the most recent distinct paper was first seen."""
    return _last_new_paper_iso


def new_papers_last_hour(now: float | None = None) -> int:
    """Count of distinct papers first seen within the last hour (the hourly rate)."""
    if now is None:
        now = datetime.now(timezone.utc).timestamp()
    cutoff = now - 3600.0
    return sum(1 for t in _seen_times if t >= cutoff)


def status_flip_counts() -> dict[str, int]:
    """Number of status-change rows logged per connection (incl. ``backend``).

    Drives the dev-ui chart comparing how often each service flips on/off.
    """
    counts: dict[str, int] = {}
    if not STATUS_LOG_CSV.exists():
        return counts
    try:
        with STATUS_LOG_CSV.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = row.get("connection")
                if name:
                    counts[name] = counts.get(name, 0) + 1
    except Exception:
        pass
    return counts


# ---------------------------------------------------------------------------
# Public API — service status changes
# ---------------------------------------------------------------------------

def record_status(connections: dict[str, dict]) -> None:
    """Append a row for every connection whose up/down status flipped.

    ``connections`` is the ``/status`` map ``{name: {"ok": bool, ...}}``. The
    first time a connection is seen it sets a silent baseline (no row); only
    actual flips are logged.
    """
    with _lock:
        now, now_iso = _now()
        rows: list[list] = []
        for name, info in connections.items():
            ok = bool(info.get("ok"))
            prev = _last_ok.get(name)
            if prev is None:
                _last_ok[name] = ok
                _last_change_at[name] = now
                continue
            if ok != prev:
                held = round(now - _last_change_at.get(name, now), 3)
                rows.append([name, now_iso, "on" if ok else "off", held])
                _last_ok[name] = ok
                _last_change_at[name] = now
        _append_rows(STATUS_LOG_CSV, _STATUS_LOG_HEADER, rows)


def record_backend_event(transition: str) -> None:
    """Log a ``backend`` on/off row (called from FastAPI startup/shutdown).

    ``seconds_since_previous`` is now minus the timestamp of the last ``backend``
    row in the log (0 if this is the first ever event).

    Crash-safe pairing: a hard kill (SIGKILL / force-terminate) can't run the
    graceful-shutdown ``off``. So on startup, if the previous instance's last
    logged backend state was still ``on``, we backfill an ``off`` (timestamped
    at detection) before the new ``on`` — guaranteeing every ``on`` is paired
    with an ``off``.
    """
    with _lock:
        now, now_iso = _now()
        rows: list[list] = []
        prev = _last_change_at.get("backend")
        if prev is None:
            # Fresh process: consult the CSV for the prior backend state.
            csv_epoch, csv_trans = _last_backend_row()
            if transition == "on" and csv_trans == "on" and csv_epoch is not None:
                rows.append(["backend", now_iso, "off", round(now - csv_epoch, 3)])
                prev = now  # the new "on" immediately follows the backfilled "off"
            else:
                prev = csv_epoch
        held = round(now - prev, 3) if prev is not None else 0.0
        rows.append(["backend", now_iso, transition, held])
        _append_rows(STATUS_LOG_CSV, _STATUS_LOG_HEADER, rows)
        _last_change_at["backend"] = now
        _last_ok["backend"] = (transition == "on")


# ---------------------------------------------------------------------------
# Test support
# ---------------------------------------------------------------------------

def reset_state() -> None:
    """Clear all in-memory tracking (used by test isolation)."""
    global _last_new_paper_iso
    _seen_sids.clear()
    _seen_uids.clear()
    _seen_times.clear()
    _last_new_paper_iso = None
    _last_ok.clear()
    _last_change_at.clear()


# Load persisted paper identities at import so the count survives restarts.
_load_seen_keys()
