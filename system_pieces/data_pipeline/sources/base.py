"""Base class + shared HTTP helpers for paper sources."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

import requests

from ..config import CONFIG
from ..models import Paper


class PaperSource(ABC):
    """Contract every source adapter implements."""

    name: str = "base"

    def __init__(self, config=CONFIG) -> None:
        self.config = config
        self._session = requests.Session()
        self._session.headers.update(
            {"User-Agent": f"{config.tool_name} (mailto:{config.contact_email})"}
        )
        self._last_request_ts = 0.0
        self._min_interval = 0.0  # seconds between requests; subclasses set this

    # --- to implement ---
    @abstractmethod
    def fetch_recent(self, query: str, *, days: int, max_results: int) -> list[Paper]:
        """Return up to `max_results` papers matching `query` from the last
        `days` days, newest first, normalized to `Paper`."""

    # --- shared plumbing ---
    def _throttle(self) -> None:
        if self._min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_request_ts
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request_ts = time.monotonic()

    def _get(self, url: str, **kwargs) -> requests.Response:
        self._throttle()
        resp = self._session.get(url, timeout=self.config.request_timeout, **kwargs)
        resp.raise_for_status()
        return resp
