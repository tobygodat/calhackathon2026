"""Data contracts for the Context Engine.

The unit of user context is a ``ContextItem``: one finding, question, or
assumption extracted from a source PDF, with the evidence that justifies it and
(once embedded) its vector. These items are what incoming data is searched
against.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass, field
from enum import Enum


class ItemKind(str, Enum):
    """The three kinds of context a paper contributes."""

    FINDING = "finding"        # a conclusion the paper makes as its point
    QUESTION = "question"      # an unknown / open problem / planned future work
    ASSUMPTION = "assumption"  # taken as true by the paper, not verified in it

    @classmethod
    def coerce(cls, value: str) -> "ItemKind":
        """Map a loose model/string label onto a known kind (defaults FINDING)."""
        v = (value or "").strip().lower()
        for kind in cls:
            if v == kind.value or v.startswith(kind.value):
                return kind
        return cls.FINDING


@dataclass
class ContextItem:
    """A single piece of extracted user context."""

    kind: ItemKind
    text: str                       # the claim, restated as a standalone sentence
    evidence: str = ""              # quote/paraphrase from the paper supporting it
    source_id: str = ""             # id of the source PDF
    source_title: str = ""          # human label for the source
    confidence: float = 0.0         # extractor confidence, 0..1
    id: str = ""                    # stable content hash, filled in __post_init__
    created_at: float = field(default_factory=time.time)
    embedding: list[float] | None = None  # populated by the engine before storing

    # --- belief-revision state (see revision.py) ---
    version: int = 1                      # bumps each time the belief is revised in place
    status: str = "active"                # active | contested | superseded
    supersedes: str | None = None         # id of the belief this one replaced, if any
    provenance: list[str] = field(default_factory=list)  # human-readable revision log

    def __post_init__(self) -> None:
        if isinstance(self.kind, str):
            self.kind = ItemKind.coerce(self.kind)
        if not self.id:
            basis = f"{self.source_id}|{self.kind.value}|{self.text}".encode("utf-8")
            self.id = hashlib.sha1(basis).hexdigest()[:16]

    def embed_text(self) -> str:
        """Text fed to the embedder — the claim plus its kind for a sharper vector."""
        return f"[{self.kind.value}] {self.text}"

    def to_dict(self, *, include_embedding: bool = False) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        if not include_embedding:
            d.pop("embedding", None)
        return d


@dataclass
class ExtractionResult:
    """Outcome of ingesting one source PDF."""

    source_id: str
    source_title: str
    items: list[ContextItem]
    used_real_model: bool          # True if Claude ran, False for the heuristic
    num_chunks: int

    def counts(self) -> dict[str, int]:
        out = {k.value: 0 for k in ItemKind}
        for it in self.items:
            out[it.kind.value] += 1
        return out
