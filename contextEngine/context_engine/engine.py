"""Top-level orchestration of the Context Initialization Engine.

``ingest_pdf`` is the upload path: PDF bytes -> text -> chunks -> extracted
findings/questions/assumptions -> embeddings -> vector store. ``search`` is the
query path that incoming data runs against the accumulated user context.
"""

from __future__ import annotations

import hashlib
import logging

from .config import SETTINGS, Settings
from .embeddings import embed_batch, embed_text
from .extractor import extract_items, using_real_model
from .models import ContextItem, ExtractionResult, ItemKind
from .pdf import chunk_text, extract_text
from .store import SearchHit, get_store

log = logging.getLogger("context_engine.engine")


def _source_id(data: bytes, title: str) -> str:
    """Stable id for a source: content hash keeps re-uploads idempotent."""
    h = hashlib.sha1(data).hexdigest()[:12]
    return f"src_{h}"


class ContextEngine:
    """Stateful facade holding a configured vector store."""

    def __init__(self, settings: Settings = SETTINGS):
        self.settings = settings
        self.store = get_store(settings)

    def ingest_pdf(self, data: bytes, title: str = "") -> ExtractionResult:
        """Ingest one PDF into the user context. Idempotent per file content."""
        text = extract_text(data)
        source_id = _source_id(data, title)
        source_title = title or source_id
        chunks = chunk_text(text, self.settings)

        items: list[ContextItem] = []
        seen: set[str] = set()
        for chunk in chunks:
            for item in extract_items(
                chunk,
                source_id=source_id,
                source_title=source_title,
                settings=self.settings,
            ):
                if item.id in seen:  # de-dupe identical claims across overlaps
                    continue
                seen.add(item.id)
                items.append(item)

        if items:
            vectors = embed_batch([it.embed_text() for it in items], self.settings)
            for it, vec in zip(items, vectors):
                it.embedding = vec
            self.store.add(items)

        return ExtractionResult(
            source_id=source_id,
            source_title=source_title,
            items=items,
            used_real_model=using_real_model(self.settings),
            num_chunks=len(chunks),
        )

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        kind: ItemKind | None = None,
        include_superseded: bool = False,
    ) -> list[SearchHit]:
        """Vector-search the user context with a free-text query.

        This is the entry point incoming data uses: embed the incoming text and
        return the most similar context items, optionally restricted to one kind.
        Superseded beliefs (replaced by a later revision) are hidden by default.
        """
        k = top_k or self.settings.search_top_k
        qvec = embed_text(query, self.settings)
        # Over-fetch so post-filtering superseded items still yields k results.
        hits = self.store.search(query, qvec, k * 3 if not include_superseded else k,
                                  kind=kind)
        if not include_superseded:
            hits = [h for h in hits if h.item.status != "superseded"]
        return hits[:k]

    def context(
        self, kind: ItemKind | None = None, *, include_superseded: bool = False
    ) -> list[ContextItem]:
        """Return all stored context items, optionally filtered by kind."""
        items = self.store.all(kind=kind)
        if not include_superseded:
            items = [it for it in items if it.status != "superseded"]
        return items

    def accept(
        self,
        text: str,
        *,
        kind: ItemKind = ItemKind.FINDING,
        source_id: str = "",
        source_title: str = "review",
        auto_apply: bool = True,
    ):
        """Accept an incoming claim and revise the context in proportion to it.

        This is the belief-revision entry point: the claim is compared to the most
        related existing belief, and (if it contradicts) the context is merged,
        forked, or superseded according to how much the claim overturns it.
        """
        from .revision import reconcile  # local import avoids a cycle at load

        incoming = ContextItem(
            kind=kind, text=text, source_id=source_id, source_title=source_title,
        )
        return reconcile(self, incoming, auto_apply=auto_apply, settings=self.settings)

    def clear(self) -> None:
        self.store.clear()
