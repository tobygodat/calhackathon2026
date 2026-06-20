# Baskr — Data Pipeline

Multi-source ingestion of recent research papers, normalized into one schema for
the Baskr engine (embed → Redis vector search → Claude classify).

**Sources:** PubMed · arXiv · bioRxiv · Nature (Crossref / Springer Nature)

Every source maps onto a single [`Paper`](models.py) shape, so downstream code
never cares where a paper came from. Results are deduped across sources by DOI
(then normalized title), so a bioRxiv preprint later published in Nature counts
once.

---

## Install

```bash
pip install -r requirements.txt    # just `requests`; XML parsing is stdlib
```

## Run

```bash
# All four sources, last 7 days
python -m implementations.data_pipeline.cli "gut microbiome immunotherapy"

# Narrow window + subset of sources, dump JSON
python -m implementations.data_pipeline.cli "amyloid clearance" \
    --days 3 --sources pubmed,biorxiv --json out.json

# Check which API keys are configured
python -m implementations.data_pipeline.cli --check
```

## Use as a library

```python
from implementations.data_pipeline import DataPipeline

pipe = DataPipeline()                                  # or DataPipeline(["pubmed"])
result = pipe.fetch("gut microbiome immunotherapy", days=7, max_per_source=50)

print(result.counts)        # {'pubmed': 50, 'arxiv': 12, ...}
print(result.errors)        # {} unless a source failed (others still return)
for paper in result.papers: # deduped, newest first
    print(paper.citation())
    paper.abstract          # -> feed to embeddings / Claude
    paper.to_dict()         # -> JSON for Redis / the frontend
```

---

## API keys — all optional

The pipeline runs against **every source with zero keys**. Keys only raise rate
limits or unlock richer abstracts. Copy `.env.example` → `.env` to add them.

| Source | Key | Needed? | Effect | Get it |
|--------|-----|---------|--------|--------|
| arXiv | — | No | — | Open API |
| bioRxiv | — | No | — | Open API |
| PubMed | `NCBI_API_KEY` | Optional | 3 → 10 req/sec | [ncbi.nlm.nih.gov/account](https://www.ncbi.nlm.nih.gov/account/) → Account Settings → **API Key Management** |
| Nature | `SPRINGER_API_KEY` | Optional | Richer abstracts/full text vs. keyless Crossref | [dev.springernature.com](https://dev.springernature.com/) → create app → copy key |

`PIPELINE_CONTACT_EMAIL` is recommended (not a key): it identifies your traffic
to NCBI and Crossref's "polite pool" so you aren't anonymously throttled.

---

## Notes / gotchas

- **arXiv query scoping.** arXiv keyword search is broad — a bare `"gut ..."`
  query can match physics "GUT" (Grand Unified Theory) papers. For the bio use
  case, scope the arXiv query, e.g. `cat:q-bio.* AND (microbiome OR immunotherapy)`.
  Pass per-source queries upstream if/when active-search needs it.
- **bioRxiv is date-range based**, not keyword based. The adapter pulls the
  window then applies a lightweight local keyword filter — ideal for the daily
  digest ("everything new today"), looser than PubMed for active search.
- **Abstracts may be missing** from some Nature/Crossref records (`[no abstract]`
  in the CLI). `paper.has_abstract` lets the engine skip or downrank them.
- Sources run in parallel; one failing source records an error in
  `result.errors` and the rest still return.

## Layout

```
data_pipeline/
├── models.py        # Paper schema + dedupe identity (uid / fingerprint)
├── config.py        # key loading from env / .env, rate limits
├── pipeline.py      # DataPipeline: fan-out, dedupe, FetchResult
├── cli.py           # python -m ...cli
└── sources/
    ├── base.py      # PaperSource ABC + throttled HTTP session
    ├── pubmed.py    # NCBI E-utilities (esearch + efetch)
    ├── arxiv.py     # arXiv Atom API
    ├── biorxiv.py   # bioRxiv/medRxiv details API
    └── nature.py    # Crossref (default) / Springer Nature (with key)
```
