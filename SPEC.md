# Baskr — Product Spec

> **Purpose:** This document is the source of truth for scaffolding the Baskr implementation repo. It defines what to build, the data contracts, the API surface, and the target file structure. This repo (claude-chats-hack) is a planning hub — no code lives here.
>
> Cal Hacks AI 2026 · tracks: Ddoski's Lab + Anthropic + Redis.

---

## 1. Product

**Baskr** is a research radar for a lab. It holds a persistent **lab context profile** — the lab's open questions, working assumptions, and prior findings — in Redis agent memory, then classifies new PubMed papers against that profile and surfaces the ones that matter, each with a one-sentence plain-language reason.

**Two surfaces, one engine:**

| Surface | Trigger | Purpose |
|---|---|---|
| **Active Search** | User submits an open question | Live, deterministic query against today's PubMed papers |
| **Daily Digest** | Scheduled / pre-generated | Surfaces relevant papers from the day's full feed with no query |

Both surfaces call the same classification engine and reason against the same profile.

---

## 2. Locked decisions

| Axis | Decision |
|---|---|
| **Name** | Baskr |
| **Niche** | Gut microbiome (~400–600 PubMed papers/day) |
| **Relationship labels** | `ANSWERS` · `CONTRADICTS` · `EXTENDS` · `NOT_RELEVANT` |
| **Stretch label** | `SCOOP` (paper pre-empts a planned experiment) — only if `planned_experiment` items exist in the profile |
| **Demo data** | Active search hits live PubMed (last 1–7 days). Digest is pre-generated and frozen. |
| **Embeddings** | OpenAI `text-embedding-3-small` (1536 dims) |
| **Reasoning LLM** | Anthropic Claude — confirm recommended model at build time |
| **Backend** | FastAPI (Python, async) |
| **Redis** | Agent Memory (profile) · RedisVL HNSW index (papers) · LangCache (query cache) |
| **Frontend** | React + Vite + TypeScript + Tailwind |

---

## 3. Open decision

**Lab context profile source** — the content of `data/profile_seed.json`:

| Option | Trade-off |
|---|---|
| Real gut-microbiome researcher (one open question + one assumption) | Highest demo authenticity; requires external lead time |
| NIH Reporter grant abstract (2024–25 Project Summary) | Real and citable; no waiting |
| Hardcoded placeholder | Fastest; weakest demo impact |

The schema (§5.1) is identical regardless of source. Scaffold against the placeholder; swap content before the demo.

---

## 4. Fact-checks (confirm before build)

- **Redis credit code + branding** — two codes appear in planning notes (`CALHACKER2026` vs. "25k from the Live Site"). Confirm from the live sponsor page.
- **Anthropic prize rule** — confirm whether it requires Claude Code specifically (not just the API) and that usage qualifies.
- **LLM model ID** — confirm current recommended `claude-*` model at build time; do not hardcode without checking.

---

## 5. Data models

### 5.1 Lab Context Profile

Stored in Redis Agent Memory (long-term), one memory per item. Mirrored in `data/profile_seed.json` for seeding.

```json
{
  "lab_id": "gut-microbiome-demo",
  "niche": "gut_microbiome",
  "display_name": "Demo Lab",
  "items": [
    { "id": "oq_1",  "kind": "open_question", "text": "..." },
    { "id": "asm_1", "kind": "assumption",     "text": "..." },
    { "id": "fnd_1", "kind": "finding",        "text": "..." }
  ]
}
```

`kind ∈ {open_question, assumption, finding, planned_experiment}`.
`planned_experiment` is required only for the `SCOOP` stretch label.

### 5.2 Paper

```json
{
  "pmid": "39876543",
  "title": "...",
  "abstract": "...",
  "authors": ["..."],
  "journal": "...",
  "pub_date": "2026-06-18",
  "url": "https://pubmed.ncbi.nlm.nih.gov/39876543/",
  "embedding": ["<1536 floats>"]
}
```

Embed the full abstract (abstracts are ~250 words; chunking not needed by default).

### 5.3 Classification result

```json
{
  "label": "CONTRADICTS",
  "reason": "One sentence: why this paper matters to this specific lab.",
  "matched_item_id": "asm_1",
  "confidence": 0.82
}
```

`label ∈ {ANSWERS, CONTRADICTS, EXTENDS, NOT_RELEVANT}`. Add `SCOOP` only with the stretch feature.

### 5.4 Digest entry (frozen for demo)

```json
{
  "date": "2026-06-19",
  "paper": "<Paper minus embedding>",
  "classification": "<Classification result>"
}
```

A day's digest is an array of `DigestEntry` containing only non-`NOT_RELEVANT` hits.

### 5.5 Redis key map

| Key | Type | Holds |
|---|---|---|
| `baskr:paper:{pmid}` | Hash | Paper metadata + embedding |
| `baskr:idx:papers` | RedisVL index | HNSW, cosine, dim 1536 |
| Agent Memory `lab:{lab_id}` | Memory namespace | Profile items |
| `baskr:digest:{date}` | String (JSON) | Frozen digest for a date |
| LangCache | managed | Semantic cache of query results |

---

## 6. Classification engine

Implemented once in `engine.py`; Active Search and Digest are thin callers.

```
classify_paper(paper, profile):
  1. embed(paper.abstract)                          # OpenAI
  2. retrieve top-k profile items from Agent Memory # k≈8, semantic
  3. build_prompt(profile_items, paper)             # §7
  4. Claude → {label, reason, matched_item_id, confidence}
  5. return classification
```

- **Active Search:** query → PubMed esearch/efetch (last 1–7 days, gut-microbiome filter) → `classify_paper` per result → return non-`NOT_RELEVANT`, sorted by confidence, capped at 5.
- **Digest (offline):** pull a day's papers → `classify_paper` per paper → write non-`NOT_RELEVANT` hits to `baskr:digest:{date}` and `data/digest_frozen/{date}.json`.
- **Memory write-back (stretch):** if a new finding is confirmed, append a `finding` item to the profile so memory visibly grows.

---

## 7. Core Claude prompt

**System:**
> You are Baskr, a research-watch agent for a gut microbiome lab. Given the lab's context profile and one new paper abstract, decide the single most important relationship between them. Be discerning — most papers are NOT_RELEVANT.

**User:**
```
LAB PROFILE:
{for each retrieved item}
- [{id} · {kind}] {text}

NEW PAPER:
Title: {title}
Abstract: {abstract}

Return strict JSON only:
{
  "label": "ANSWERS|CONTRADICTS|EXTENDS|NOT_RELEVANT",
  "reason": "<one sentence why it matters to THIS lab, naming the matched item>",
  "matched_item_id": "<profile item id, or null if NOT_RELEVANT>",
  "confidence": <0.0–1.0>
}
```

Enforce JSON output (tool use or `response_format`). Treat confidence below 0.5 as `NOT_RELEVANT`.

---

## 8. Backend API (FastAPI)

| Method | Route | Input | Output |
|---|---|---|---|
| `GET` | `/api/health` | — | `{status: "ok"}` |
| `GET` | `/api/profile` | — | Lab profile (§5.1) |
| `POST` | `/api/search` | `{question: str}` | `[{paper, classification}]` (≤5, live) |
| `GET` | `/api/digest/history` | — | `[{date, count, top_label}]` |
| `GET` | `/api/digest/{date}` | — | `DigestEntry[]` (frozen) |
| `POST` | `/api/profile/memory` *(stretch)* | `{kind, text}` | Updated profile |

CORS open to the Vite dev origin. No auth.

---

## 9. Frontend (three panels)

Dark research-tool styling. All panels on one page.

| Component | Purpose |
|---|---|
| `LabProfilePanel` | Renders profile items grouped by `kind`. First thing the judge sees. |
| `ActiveSearchPanel` | Text input → `POST /api/search` → `PaperCard` list |
| `DigestHistoryPanel` | Date list from `/api/digest/history`; clicking loads `/api/digest/{date}` |
| `PaperCard` | Title, citation, `LabelBadge`, one-sentence reason, PubMed link |
| `LabelBadge` | Colored chip: `CONTRADICTS`=red, `ANSWERS`=green, `EXTENDS`=blue, `NOT_RELEVANT`=gray |

---

## 10. Target file structure (for the implementation repo)

```
baskr/
├── .env.example
├── README.md
│
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py          # FastAPI app + all routes (§8)
│       ├── config.py        # env vars, model names, thresholds
│       ├── models.py        # Pydantic: Profile, Paper, Classification, DigestEntry
│       ├── redis_client.py  # Redis connection; create/load RedisVL index
│       ├── pubmed.py        # NCBI E-utilities: esearch + efetch
│       ├── embeddings.py    # OpenAI text-embedding-3-small wrapper
│       ├── llm.py           # Anthropic client, JSON-enforced output
│       ├── prompts.py       # build_prompt() (§7)
│       ├── memory.py        # Agent Memory R/W
│       ├── engine.py        # classify_paper() (§6) — shared by both surfaces
│       ├── ingest.py        # PubMed pull → embed → bulk-load RedisVL
│       └── seed_profile.py  # load data/profile_seed.json → Agent Memory
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx          # three-panel layout
│       ├── api.ts           # typed fetch wrappers for §8
│       ├── types.ts         # mirrors models.py
│       └── components/
│           ├── LabProfilePanel.tsx
│           ├── ActiveSearchPanel.tsx
│           ├── DigestHistoryPanel.tsx
│           ├── PaperCard.tsx
│           └── LabelBadge.tsx
│
├── data/
│   ├── profile_seed.json        # lab profile (source = §3 open decision)
│   └── digest_frozen/           # {date}.json pre-generated digests
│
└── scripts/
    └── freeze_digest.py         # offline: generate + write N days of frozen digest
```

**Build dependency order:** `config` → `redis_client` + `pubmed` + `embeddings` + `llm` → `prompts` + `memory` → `engine` → `main` → `ingest` / `seed_profile` / `freeze_digest` → frontend.

---

## 11. Environment (`.env.example`)

```
NCBI_API_KEY=             # free; raises rate limit ~3→~10 req/sec
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
REDIS_URL=
BASKR_LAB_ID=gut-microbiome-demo
BASKR_RELEVANCE_THRESHOLD=0.5
EMBED_MODEL=text-embedding-3-small
REASON_MODEL=             # confirm at build time (§4)
```

---

## 12. Scope

| ✅ In | ❌ Out |
|---|---|
| Gut microbiome only | Other niches / configurability |
| Live active search + frozen digest | Fully live digest on stage |
| `ANSWERS/CONTRADICTS/EXTENDS/NOT_RELEVANT` | `SCOOP` + planned experiments (stretch only) |
| PubMed only | arXiv / bioRxiv / Nature |
| Single lab, no auth | Multi-lab, accounts, settings |
| `text-embedding-3-small` | Other embedding models |
| Batch digest generation | Real-time Redis Streams (stretch only) |
