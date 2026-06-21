"""Unit tests for app/monitoring.py (new-papers + service-status CSV logs).

The module keeps state in module-level sets/dicts and writes to module-level CSV
path constants. Each test repoints those constants at its own tmp_path and resets
the in-memory state so tests are independent. (The autouse conftest fixture
already isolates paths globally; these tests pin them per-test for clarity.)
"""

from __future__ import annotations

import csv

import pytest

import app.monitoring as mon


@pytest.fixture
def csvs(tmp_path, monkeypatch):
    """Repoint both CSV logs at tmp_path and reset in-memory state."""
    papers = tmp_path / "new_papers_seen.csv"
    status = tmp_path / "service_status_log.csv"
    monkeypatch.setattr(mon, "NEW_PAPERS_CSV", papers)
    monkeypatch.setattr(mon, "STATUS_LOG_CSV", status)
    mon.reset_state()
    yield papers, status
    mon.reset_state()


def _rows(path):
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _paper(source="pubmed", source_id="1", title="T", uid=None):
    return {"source": source, "source_id": source_id, "title": title, "uid": uid}


# ---------------------------------------------------------------------------
# record_papers / seen_count
# ---------------------------------------------------------------------------

class TestRecordPapers:
    def test_appends_new_and_counts(self, csvs):
        papers_csv, _ = csvs
        total = mon.record_papers([_paper(source_id="1"), _paper(source_id="2")])
        assert total == 2
        assert mon.seen_count() == 2
        rows = _rows(papers_csv)
        assert len(rows) == 2
        assert set(rows[0]) == {"first_seen_at", "source", "source_id", "title"}

    def test_dedups_within_and_across_calls(self, csvs):
        papers_csv, _ = csvs
        mon.record_papers([_paper(source_id="1"), _paper(source_id="1")])  # dup in batch
        assert mon.seen_count() == 1
        # Same paper again in a later call -> no new row.
        total = mon.record_papers([_paper(source_id="1"), _paper(source_id="3")])
        assert total == 2
        assert mon.seen_count() == 2
        assert len(_rows(papers_csv)) == 2

    def test_dedups_by_uid(self, csvs):
        # Same uid but different source/source_id should not be double counted.
        mon.record_papers([_paper(source="biorxiv", source_id="a", uid="doi:10.1/x")])
        total = mon.record_papers([_paper(source="pubmed", source_id="b", uid="doi:10.1/x")])
        assert total == 1
        assert mon.seen_count() == 1

    def test_count_survives_restart_via_reload(self, csvs):
        papers_csv, _ = csvs
        mon.record_papers([_paper(source_id="1"), _paper(source_id="2")])
        # Simulate a process restart: wipe memory, reload from the CSV.
        mon.reset_state()
        assert mon.seen_count() == 0
        mon._load_seen_keys()
        assert mon.seen_count() == 2
        # A previously-seen paper is still recognised as not-new.
        assert mon.record_papers([_paper(source_id="1")]) == 2


# ---------------------------------------------------------------------------
# record_status
# ---------------------------------------------------------------------------

class TestRecordStatus:
    def test_baseline_writes_no_row(self, csvs):
        _, status_csv = csvs
        mon.record_status({"redis": {"ok": True}, "pubmed": {"ok": False}})
        assert not status_csv.exists()  # nothing written for the first observation

    def test_no_row_when_unchanged(self, csvs):
        _, status_csv = csvs
        mon.record_status({"redis": {"ok": True}})
        mon.record_status({"redis": {"ok": True}})
        assert not status_csv.exists()

    def test_flip_writes_row_with_transition_and_held_time(self, csvs):
        _, status_csv = csvs
        mon.record_status({"redis": {"ok": True}})   # baseline on
        mon.record_status({"redis": {"ok": False}})  # flip off
        mon.record_status({"redis": {"ok": True}})   # flip on
        rows = _rows(status_csv)
        assert [r["connection"] for r in rows] == ["redis", "redis"]
        assert [r["transition"] for r in rows] == ["off", "on"]
        for r in rows:
            assert set(r) == {"connection", "changed_at", "transition",
                              "seconds_since_previous"}
            assert float(r["seconds_since_previous"]) >= 0.0

    def test_each_connection_tracked_independently(self, csvs):
        _, status_csv = csvs
        mon.record_status({"redis": {"ok": True}, "anthropic": {"ok": True}})
        mon.record_status({"redis": {"ok": False}, "anthropic": {"ok": True}})
        rows = _rows(status_csv)
        assert len(rows) == 1
        assert rows[0]["connection"] == "redis"
        assert rows[0]["transition"] == "off"


# ---------------------------------------------------------------------------
# record_backend_event
# ---------------------------------------------------------------------------

class TestRecordBackendEvent:
    def test_on_then_off_rows(self, csvs):
        _, status_csv = csvs
        mon.record_backend_event("on")
        mon.record_backend_event("off")
        rows = _rows(status_csv)
        assert [r["connection"] for r in rows] == ["backend", "backend"]
        assert [r["transition"] for r in rows] == ["on", "off"]
        # First event has no prior backend row -> 0; second is non-negative.
        assert float(rows[0]["seconds_since_previous"]) == 0.0
        assert float(rows[1]["seconds_since_previous"]) >= 0.0

    def test_seconds_since_previous_seeded_from_csv_after_restart(self, csvs):
        _, status_csv = csvs
        mon.record_backend_event("on")
        # Simulate restart: clear memory; the next event must read the last
        # backend row from the CSV to compute elapsed time (not 0).
        mon.reset_state()
        mon.record_backend_event("off")
        rows = _rows(status_csv)
        assert len(rows) == 2
        assert float(rows[1]["seconds_since_previous"]) >= 0.0

    def test_hard_kill_backfills_off_on_next_startup(self, csvs):
        """If the prior instance was force-killed (last backend row still 'on'),
        a fresh startup backfills an 'off' before the new 'on'."""
        _, status_csv = csvs
        mon.record_backend_event("on")
        # Simulate a hard kill: no graceful "off" was written; clear memory.
        mon.reset_state()
        mon.record_backend_event("on")
        rows = _rows(status_csv)
        # on (1st run) -> backfilled off -> on (2nd run)
        assert [r["transition"] for r in rows] == ["on", "off", "on"]
        assert [r["connection"] for r in rows] == ["backend", "backend", "backend"]
        assert float(rows[1]["seconds_since_previous"]) >= 0.0


# ---------------------------------------------------------------------------
# Time-based paper metrics
# ---------------------------------------------------------------------------

class TestPaperTimeMetrics:
    def test_last_new_paper_at_set_on_record(self, csvs):
        assert mon.last_new_paper_at() is None
        mon.record_papers([_paper(source_id="1")])
        assert mon.last_new_paper_at() is not None
        assert mon.last_new_paper_at().endswith("Z")

    def test_new_papers_last_hour_counts_recent(self, csvs):
        mon.record_papers([_paper(source_id="1"), _paper(source_id="2")])
        # Both just recorded -> within the last hour.
        assert mon.new_papers_last_hour() == 2
        # Looking from two hours in the future -> none are recent.
        import time
        assert mon.new_papers_last_hour(now=time.time() + 7200) == 0

    def test_metrics_survive_reload_from_csv(self, csvs):
        mon.record_papers([_paper(source_id="1"), _paper(source_id="2")])
        # Simulate restart: drop memory, reload from the CSV.
        mon.reset_state()
        mon._load_seen_keys()
        assert mon.seen_count() == 2
        assert mon.last_new_paper_at() is not None
        assert mon.new_papers_last_hour() == 2


# ---------------------------------------------------------------------------
# status_flip_counts
# ---------------------------------------------------------------------------

class TestStatusFlipCounts:
    def test_empty_when_no_log(self, csvs):
        assert mon.status_flip_counts() == {}

    def test_counts_rows_per_connection(self, csvs):
        mon.record_backend_event("on")
        # Baseline (no rows), then two flips for redis, one for pubmed.
        mon.record_status({"redis": {"ok": True}, "pubmed": {"ok": True}})
        mon.record_status({"redis": {"ok": False}, "pubmed": {"ok": True}})
        mon.record_status({"redis": {"ok": True}, "pubmed": {"ok": False}})
        counts = mon.status_flip_counts()
        assert counts["backend"] == 1
        assert counts["redis"] == 2   # off then on
        assert counts["pubmed"] == 1  # on -> off once


# ---------------------------------------------------------------------------
# paper_ledger
# ---------------------------------------------------------------------------

class TestPaperLedger:
    def test_empty_when_no_csv(self, csvs):
        assert mon.paper_ledger() == []

    def test_returns_newest_first_with_three_fields(self, csvs):
        mon.record_papers([_paper(source="pubmed", source_id="1", title="Older")])
        mon.record_papers([_paper(source="arxiv", source_id="2", title="Newer")])
        ledger = mon.paper_ledger()
        assert [r["title"] for r in ledger] == ["Newer", "Older"]
        for r in ledger:
            assert set(r) == {"title", "first_seen_at", "source"}
            assert r["first_seen_at"].endswith("Z")
        assert ledger[0]["source"] == "arxiv"


# ---------------------------------------------------------------------------
# seconds_since_last_new_paper
# ---------------------------------------------------------------------------

class TestSecondsSinceLastNewPaper:
    def test_none_when_no_papers(self, csvs):
        assert mon.seconds_since_last_new_paper() is None

    def test_zero_ish_right_after_record(self, csvs):
        mon.record_papers([_paper(source_id="1")])
        secs = mon.seconds_since_last_new_paper()
        assert isinstance(secs, int)
        assert secs >= 0

    def test_grows_with_now(self, csvs):
        import time
        mon.record_papers([_paper(source_id="1")])
        secs = mon.seconds_since_last_new_paper(now=time.time() + 120)
        assert secs >= 120


# ---------------------------------------------------------------------------
# recent_status_flips
# ---------------------------------------------------------------------------

class TestRecentStatusFlips:
    def test_empty_when_no_log(self, csvs):
        assert mon.recent_status_flips() == []

    def test_chronological_with_three_fields(self, csvs):
        mon.record_status({"redis": {"ok": True}})   # baseline (no row)
        mon.record_status({"redis": {"ok": False}})  # off
        mon.record_status({"redis": {"ok": True}})   # on
        flips = mon.recent_status_flips()
        assert [f["transition"] for f in flips] == ["off", "on"]
        for f in flips:
            assert set(f) == {"connection", "changed_at", "transition"}

    def test_limit_keeps_most_recent(self, csvs):
        mon.record_status({"redis": {"ok": True}})  # baseline
        for i in range(5):
            mon.record_status({"redis": {"ok": i % 2 == 0}})
        flips = mon.recent_status_flips(limit=2)
        assert len(flips) == 2
