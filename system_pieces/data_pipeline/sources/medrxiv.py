"""medRxiv source — the medRxiv server of the shared bioRxiv details API. No API key."""
from __future__ import annotations

from .biorxiv import BioRxivSource


class MedRxivSource(BioRxivSource):
    name = "medrxiv"

    def __init__(self, config=None) -> None:
        super().__init__(config, server="medrxiv")
