"""Extract findings, questions, and assumptions from paper text.

Two paths, one signature (``extract_items``):

- **Real (Anthropic key present):** Claude reads a chunk and emits its items via
  a single forced tool call whose ``input_schema`` is the item contract, so the
  output is always schema-valid JSON (no brittle text parsing).
- **Degraded (no key):** a deterministic sentence-level heuristic that classifies
  sentences by cue phrases into the three kinds. Clearly a stand-in, but keeps the
  engine fully runnable offline and in tests.

Definitions held constant across both paths:
- finding    — a conclusion the paper makes as its central point.
- question   — an unknown, open problem, or planned future experiment/research.
- assumption — a fact taken as true by the paper but NOT verified within it.
"""

from __future__ import annotations

import re
import time

from .config import SETTINGS, Settings
from .models import ContextItem, ItemKind

# --- Anthropic backoff (mirrors baskr/app/llm.py resilience) ---------------
_RETRY_STATUS = frozenset({429, 500, 502, 503, 529})
_RETRY_EXC_NAMES = frozenset({
    "RateLimitError", "OverloadedError", "InternalServerError",
    "APITimeoutError", "APIConnectionError",
})
_MAX_RETRIES = 5
_BASE_BACKOFF = 0.5

_SYSTEM = (
    "You build a researcher's working context from their papers. For the given "
    "text, extract three kinds of statements, each rewritten as a clear, "
    "standalone sentence that makes sense without the surrounding paper:\n"
    "- finding: a CONCLUSION the paper asserts as its point (a result it stands "
    "behind), not background or another work's result.\n"
    "- question: an UNKNOWN the paper raises — an open problem, a limitation left "
    "unresolved, or an explicitly planned future experiment or line of research.\n"
    "- assumption: a fact the paper TAKES AS TRUE to make its argument but does "
    "NOT itself verify or test (premises, modeling choices, accepted prior claims).\n"
    "Only extract statements actually supported by the text. If a kind is absent, "
    "return none of it. Prefer precision over recall; do not invent. For each item "
    "give a short supporting quote or close paraphrase as evidence."
)

_EXTRACT_TOOL = {
    "name": "record_context_items",
    "description": "Record the findings, questions, and assumptions found in the text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {
                            "type": "string",
                            "enum": ["finding", "question", "assumption"],
                        },
                        "text": {
                            "type": "string",
                            "description": "The statement as a standalone sentence.",
                        },
                        "evidence": {
                            "type": "string",
                            "description": "Short supporting quote/paraphrase from the text.",
                        },
                        "confidence": {
                            "type": "number", "minimum": 0.0, "maximum": 1.0,
                        },
                    },
                    "required": ["kind", "text", "evidence", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    },
}


def _is_retryable(exc: Exception) -> bool:
    if getattr(exc, "status_code", None) in _RETRY_STATUS:
        return True
    return type(exc).__name__ in _RETRY_EXC_NAMES


def _create_with_backoff(client, **kwargs):
    last: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            if not _is_retryable(exc):
                raise
            last = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_BASE_BACKOFF * (2 ** attempt))
    raise RuntimeError(f"Anthropic extraction failed after {_MAX_RETRIES} attempts: {last}")


def _extract_real(chunk: str, settings: Settings) -> list[dict]:
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    user = (
        f"Extract at most {settings.max_items_per_chunk} of the most important "
        f"items from this text:\n\n{chunk}"
    )
    resp = _create_with_backoff(
        client,
        model=settings.extract_model,
        max_tokens=2048,
        system=_SYSTEM,
        tools=[_EXTRACT_TOOL],
        tool_choice={"type": "tool", "name": _EXTRACT_TOOL["name"]},
        messages=[{"role": "user", "content": user}],
    )
    tool_use = next(b for b in resp.content if b.type == "tool_use")
    return tool_use.input.get("items", [])


# --- deterministic degraded path -------------------------------------------

_SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

# Cue phrases that signal each kind. Ordered so question/assumption (more
# specific) win over the broad finding cues when a sentence matches several.
_QUESTION_CUES = (
    "remains unknown", "remains unclear", "is unclear", "future work", "future research",
    "further work", "further research", "further study", "future studies",
    "open question", "it is unknown", "not yet known", "warrants", "future experiments",
    "needs to be", "remains to be", "yet to be", "whether ", "could be explored",
    "should be investigated", "we plan to", "we will investigate",
)
_ASSUMPTION_CUES = (
    "we assume", "assuming", "is assumed", "we posit", "we suppose", "given that",
    "taken as", "is taken to be", "for simplicity", "we treat", "is known to",
    "it is well established", "it is well known", "by assumption", "presumably",
    "we hypothesize", "we hypothesise", "is expected to",
)
_FINDING_CUES = (
    "we find", "we found", "we show", "we showed", "we demonstrate", "we observe",
    "we observed", "we conclude", "our results", "these results", "results show",
    "we report", "indicates that", "suggests that", "demonstrates that",
    "we establish", "this shows", "confirms that", "in conclusion",
)


def _classify_sentence(sent_lc: str) -> ItemKind | None:
    if any(c in sent_lc for c in _QUESTION_CUES) or sent_lc.rstrip().endswith("?"):
        return ItemKind.QUESTION
    if any(c in sent_lc for c in _ASSUMPTION_CUES):
        return ItemKind.ASSUMPTION
    if any(c in sent_lc for c in _FINDING_CUES):
        return ItemKind.FINDING
    return None


def _extract_degraded(chunk: str, settings: Settings) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    for sent in _SENT_RE.split(chunk):
        sent = sent.strip()
        if not (25 <= len(sent) <= 400):  # skip fragments and runaway blocks
            continue
        kind = _classify_sentence(sent.lower())
        if kind is None:
            continue
        key = sent[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "kind": kind.value,
            "text": sent,
            "evidence": "[heuristic] matched cue phrase in source sentence",
            "confidence": 0.4,
        })
        if len(items) >= settings.max_items_per_chunk:
            break
    return items


def extract_items(
    chunk: str,
    *,
    source_id: str,
    source_title: str,
    settings: Settings = SETTINGS,
) -> list[ContextItem]:
    """Extract context items from one chunk of paper text.

    Uses Claude when an Anthropic key is configured; on failure or no key, falls
    back to the deterministic heuristic so a result is always produced.
    """
    raw: list[dict]
    if settings.anthropic_api_key:
        try:
            raw = _extract_real(chunk, settings)
        except Exception:  # noqa: BLE001 - degrade rather than fail the upload
            raw = _extract_degraded(chunk, settings)
    else:
        raw = _extract_degraded(chunk, settings)

    out: list[ContextItem] = []
    for r in raw:
        text = (r.get("text") or "").strip()
        if not text:
            continue
        out.append(ContextItem(
            kind=ItemKind.coerce(r.get("kind", "finding")),
            text=text,
            evidence=(r.get("evidence") or "").strip(),
            source_id=source_id,
            source_title=source_title,
            confidence=float(r.get("confidence", 0.0) or 0.0),
        ))
    return out


def using_real_model(settings: Settings = SETTINGS) -> bool:
    return bool(settings.anthropic_api_key)
