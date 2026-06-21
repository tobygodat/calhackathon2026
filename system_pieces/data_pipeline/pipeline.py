"""Pipeline orchestrator.

Fans a single query out across every configured source, normalizes the results
into `Paper` objects, dedupes across sources (a bioRxiv preprint later published
in a journal is one paper), and hands back a clean list ready for the engine:
embed -> Redis vector search -> Claude classify.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from .config import CONFIG, Config
from .models import Paper
from .sources import SOURCE_REGISTRY, PaperSource

log = logging.getLogger("baskr.pipeline")


@dataclass
class FetchResult:
    papers: list[Paper] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)   # source -> error message
    counts: dict[str, int] = field(default_factory=dict)   # source -> kept count

    def __len__(self) -> int:
        return len(self.papers)


class DataPipeline:
    def __init__(self, sources: list[str] | None = None, config: Config = CONFIG) -> None:
        names = sources or list(SOURCE_REGISTRY)
        unknown = set(names) - set(SOURCE_REGISTRY)
        if unknown:
            raise ValueError(f"Unknown source(s): {sorted(unknown)}. "
                             f"Available: {sorted(SOURCE_REGISTRY)}")
        self.config = config
        self.sources: dict[str, PaperSource] = {n: SOURCE_REGISTRY[n](config) for n in names}

    def fetch(
        self,
        query: str,
        *,
        days: int | None = None,
        max_per_source: int | None = None,
        parallel: bool = True,
    ) -> FetchResult:
        """Fetch recent papers for `query` across all configured sources."""
        days = days or self.config.default_lookback_days
        max_per_source = max_per_source or self.config.default_max_per_source
        result = FetchResult()

        def run(name: str, src: PaperSource) -> tuple[str, list[Paper], str | None]:
            try:
                papers = src.fetch_recent(query, days=days, max_results=max_per_source)
                log.info("%s: fetched %d papers", name, len(papers))
                return name, papers, None
            except Exception as exc:  # one source failing must not sink the rest
                log.warning("%s failed: %s", name, exc)
                return name, [], f"{type(exc).__name__}: {exc}"

        gathered: list[Paper] = []
        if parallel:
            with ThreadPoolExecutor(max_workers=len(self.sources)) as pool:
                futures = [pool.submit(run, n, s) for n, s in self.sources.items()]
                outcomes = [f.result() for f in as_completed(futures)]
        else:
            outcomes = [run(n, s) for n, s in self.sources.items()]

        for name, papers, error in outcomes:
            if error:
                result.errors[name] = error
            result.counts[name] = len(papers)
            gathered.extend(papers)

        result.papers = self._dedupe(gathered)
        return result

    @staticmethod
    def _dedupe(papers: list[Paper]) -> list[Paper]:
        """Collapse duplicates by DOI first, then by normalized-title hash.
        Keep the copy with the longest abstract (most signal for the model).

        Algorithm:
        1. Build a uid→best map and a fingerprint→best map in tandem.
           When the same fingerprint appears under multiple UIDs, the
           fingerprint map always holds the winner (longest abstract).
        2. Emit only the papers that the fingerprint map agrees are the
           canonical representative — this prevents a paper that lost on
           fingerprint from sneaking through via its uid key.
        """
        best_by_uid: dict[str, Paper] = {}
        best_by_fp: dict[str, Paper] = {}

        for p in papers:
            fp = f"fp:{p.fingerprint}"
            # uid slot
            existing_uid = best_by_uid.get(p.uid)
            if existing_uid is None or len(p.abstract) > len(existing_uid.abstract):
                best_by_uid[p.uid] = p
            # fingerprint slot
            existing_fp = best_by_fp.get(fp)
            if existing_fp is None or len(p.abstract) > len(existing_fp.abstract):
                best_by_fp[fp] = p

        # The fingerprint map is the authority for cross-source dedup.
        # Only include a uid-winner if it is also the fingerprint-winner for
        # its title cluster.
        fp_winners: set[int] = {id(p) for p in best_by_fp.values()}

        seen: set[int] = set()
        deduped: list[Paper] = []
        for p in best_by_uid.values():
            fp_winner = best_by_fp.get(f"fp:{p.fingerprint}")
            # Prefer the fingerprint-winner object; only fall back to the
            # uid-winner if no fingerprint winner exists (shouldn't happen).
            canonical = fp_winner if fp_winner is not None else p
            if id(canonical) in seen:
                continue
            seen.add(id(canonical))
            deduped.append(canonical)

        deduped.sort(key=lambda p: p.published or "", reverse=True)
        return deduped
