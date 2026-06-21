# do not include in test1
"""Classification engine — implemented once, shared by both surfaces (SPEC §6).

    classify_paper(paper, profile):
      1. retrieve top-k profile items from memory       # memory.py
      2. (opt-in) search prior work via Redis vector index   # redis_client.py
      3. build_prompt(profile_items, paper, prior_work)  # prompts.py (§7)
      4. Claude -> {label, reason, matched_item_id, confidence}   # llm.py
      5. return classification

The prior-work step is gated on ``settings.use_vector_priorwork`` (env
``BASKR_USE_VECTOR_PRIORWORK``, default OFF). When off, classify_paper runs
entirely through Anthropic with no Redis vector round-trip and behaves exactly as
before. When on, the paper abstract is embedded locally (app/embeddings.py) and
``redis_client.query_similar`` supplies the top-N similar prior papers; any
failure there falls back transparently to the no-prior-work prompt.

Throughput (see ARCHITECTURE_DECISIONS.md #12): classification is the cost and
latency bottleneck, so both surfaces fan ``classify_paper`` out with bounded
concurrency instead of a serial for-loop, and ``active_search`` runs a cheap,
keyless pre-filter so the LLM only ever sees the most promising candidates —
cost scales with output size, not fetch size.

Paper fetching is delegated to ingest.py (DataPipeline adapter).
"""

from __future__ import annotations

import concurrent.futures
import math
import re

from .config import SETTINGS, Settings
from .models import Classification, Label, PaperOut, Profile, SearchHit

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _search_prior_work(paper: PaperOut,
                       settings: Settings) -> list[dict] | None:
    """Opt-in agent-loop step: embed the paper and fetch similar prior papers.

    Returns the top-N prior-work records from the Redis vector index, or None when
    the feature is off, there is no text to embed, or anything fails — every
    failure mode collapses to "no prior work" so classification never breaks on a
    missing/unhealthy vector index.
    """
    if not settings.use_vector_priorwork:
        return None
    text = paper.abstract or paper.title
    if not text:
        return None
    try:
        from .embeddings import embed_text  # noqa: PLC0415
        from .redis_client import query_similar  # noqa: PLC0415

        embedding = embed_text(text, settings)
        return query_similar(embedding, settings.vector_priorwork_k, settings=settings)
    except Exception:  # noqa: BLE001 — any failure -> no-prior-work prompt
        return None


def classify_paper(paper: PaperOut, profile: Profile,
                   settings: Settings = SETTINGS) -> Classification:
    """Run the engine for one paper against the lab profile (SPEC §6)."""
    from .llm import classify
    from .memory import retrieve_relevant
    from .prompts import build_prompt

    # Step 1: retrieve relevant profile items
    items = retrieve_relevant(paper.abstract or paper.title, settings=settings)

    # Step 2: search prior work (opt-in; None when disabled or on failure)
    prior_work = _search_prior_work(paper, settings)

    # Step 3: build prompt
    system, user = build_prompt(items, paper, prior_work=prior_work)

    # Step 4: call Claude
    classification = classify(system, user, settings=settings)

    return classification


# --- bounded-concurrency fan-out -------------------------------------------

def _classify_concurrent(
    papers: list[PaperOut], profile: Profile, settings: Settings
) -> list[Classification]:
    """Classify ``papers`` against ``profile`` with bounded concurrency.

    ``classify_paper`` is a synchronous (blocking) Claude call, so the fan-out is
    a thread pool capped at ``settings.classify_concurrency`` rather than an
    asyncio gather. ``ThreadPoolExecutor.map`` preserves input order, so the i-th
    result lines up with the i-th paper. A per-paper failure collapses to a
    NOT_RELEVANT stand-in so one bad paper never sinks the whole batch. This path
    is identical in degraded mode (the fake classifier is just as concurrent).
    """
    if not papers:
        return []

    def _one(paper: PaperOut) -> Classification:
        try:
            return classify_paper(paper, profile, settings=settings)
        except Exception as exc:  # noqa: BLE001 — degrade one paper, not the batch
            return Classification(
                label=Label.NOT_RELEVANT,
                reason=f"Classification unavailable: {exc}",
                matched_item_id=None,
                confidence=0.0,
            )

    # Never spin up more workers than there is work for, and always at least 1.
    workers = min(max(1, settings.classify_concurrency), len(papers))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_one, papers))


# --- cheap pre-filter (LLM-free candidate ranking) -------------------------

def _paper_text(paper: PaperOut) -> str:
    return f"{paper.title} {paper.abstract}".strip()


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors (0.0 on degenerate input)."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _vector_scores(
    query: str, papers: list[PaperOut], settings: Settings
) -> list[float] | None:
    """Per-paper relevance via local embedding cosine vs the query (cheap signal).

    Returns ``None`` to signal "fall back to lexical" when embeddings are
    unavailable. The keyless hashed embedder is deterministic, so this vector
    path (the same similarity notion ``redis_client.query_similar`` uses) runs in
    degraded mode too — no Redis round-trip, since freshly fetched papers are not
    yet indexed.
    """
    try:
        from .embeddings import embed_batch, embed_text  # noqa: PLC0415

        query_vec = embed_text(query, settings)
        paper_vecs = embed_batch([_paper_text(p) for p in papers], settings)
    except Exception:  # noqa: BLE001 — any embedding failure -> lexical fallback
        return None

    if not query_vec or len(paper_vecs) != len(papers):
        return None
    return [_cosine(query_vec, v) for v in paper_vecs]


def _lexical_scores(query: str, papers: list[PaperOut]) -> list[float]:
    """Jaccard token-overlap of the query against each paper (no embeddings).

    Mirrors the lexical fallback ranker in ``memory.retrieve_relevant`` so the
    keyless path ranks consistently with the rest of the system.
    """
    q = set(_TOKEN_RE.findall(query.lower()))
    scores: list[float] = []
    for paper in papers:
        p = set(_TOKEN_RE.findall(_paper_text(paper).lower()))
        union = len(q | p)
        scores.append(len(q & p) / union if union else 0.0)
    return scores


def _prefilter(
    query: str, papers: list[PaperOut], cap: int, settings: Settings
) -> list[PaperOut]:
    """Rank fetched papers by a cheap, LLM-free signal; keep the top ``cap``.

    This is the cost guardrail for ``active_search``: the LLM must never run on
    more than ``cap`` papers regardless of fetch size. Vector similarity is the
    primary signal; lexical Jaccard is the fallback when embeddings are
    unavailable. Ties break toward the original fetch order for determinism.
    """
    cap = max(0, cap)
    if len(papers) <= cap:
        return papers

    scores = _vector_scores(query, papers, settings)
    if scores is None:
        scores = _lexical_scores(query, papers)

    # Highest score first; stable on ties via the original index.
    order = sorted(range(len(papers)), key=lambda i: (-scores[i], i))
    return [papers[i] for i in order[:cap]]


# --- surfaces --------------------------------------------------------------

def active_search(question: str, settings: Settings = SETTINGS) -> list[SearchHit]:
    """Live surface: fetch recent papers, classify the most promising, return hits.

    Cost/latency are bounded two ways: a cheap keyless pre-filter caps how many
    papers reach the LLM (``settings.preclassify_cap``), and the surviving
    classifications run with bounded concurrency. The final relevance filter,
    confidence sort, and ``active_search_cap`` are unchanged.
    """
    from .ingest import fetch_recent
    from .memory import load_profile

    profile = load_profile(settings=settings)

    # Build a gut-microbiome focused query combining the user question
    gut_query = f"gut microbiome {question}" if "microbiome" not in question.lower() else question

    papers = fetch_recent(
        query=gut_query,
        days=settings.active_search_days,
        max_per_source=20,
        settings=settings,
    )

    # Cheap pre-filter BEFORE any LLM call: rank by vector/lexical similarity and
    # keep only the top preclassify_cap candidates. The LLM never sees more.
    candidates = _prefilter(gut_query, papers, settings.preclassify_cap, settings)

    classifications = _classify_concurrent(candidates, profile, settings)

    hits = [
        SearchHit(paper=paper, classification=cl)
        for paper, cl in zip(candidates, classifications)
        if cl.label != Label.NOT_RELEVANT
    ]

    # Sort by confidence descending, cap at active_search_cap
    hits.sort(key=lambda h: h.classification.confidence, reverse=True)
    return hits[: settings.active_search_cap]


def run_digest(date: str, papers: list[PaperOut],
               settings: Settings = SETTINGS) -> list[SearchHit]:
    """Offline surface: classify a day's papers, keep non-NOT_RELEVANT hits.

    No pre-filter (a digest reports on every paper of the day), but classification
    runs with bounded concurrency instead of a serial loop. The relative order of
    the surviving hits matches the input order.
    """
    from .memory import load_profile

    profile = load_profile(settings=settings)
    classifications = _classify_concurrent(papers, profile, settings)
    return [
        SearchHit(paper=paper, classification=cl)
        for paper, cl in zip(papers, classifications)
        if cl.label != Label.NOT_RELEVANT
    ]
