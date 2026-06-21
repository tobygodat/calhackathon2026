"""In-process store for the last pipeline search result (surfaced in /status metrics)."""

from __future__ import annotations

from typing import Any

_state: dict[str, Any] = {}


def update(
    query: str,
    result_count: int,
    source_counts: dict[str, int],
    source_errors: dict[str, str],
    dedupe_ratio: float,
) -> None:
    _state.update(
        pipeline_last_query=query,
        pipeline_last_result_count=result_count,
        pipeline_source_counts=source_counts,
        pipeline_source_errors=source_errors,
        pipeline_dedupe_ratio=dedupe_ratio,
    )


def get() -> dict[str, Any]:
    return dict(_state)
