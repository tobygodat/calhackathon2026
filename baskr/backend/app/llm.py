# do not include in test1
"""Anthropic Claude client with JSON-enforced output (SPEC §7).

Sends the system+user prompt from ``prompts.build_prompt`` and parses a strict
``Classification``. Two paths, same signature:

- **Real (key present):** Anthropic Messages API with ``settings.reason_model``.
  JSON output is ENFORCED via **tool use** — a single tool whose ``input_schema``
  is the Classification contract, forced with ``tool_choice={"type": "tool"}``.
  The model can only answer by emitting a tool call matching the schema, so the
  parsed ``input`` is always schema-valid JSON (no brittle text parsing).
- **Degraded (no key):** a deterministic, rule-based classifier that scores the
  paper text against the profile items embedded in the user prompt via simple
  lexical overlap and returns a valid ``Classification``. Clearly a stand-in.

In BOTH paths the threshold-collapse rule is applied centrally in
``_apply_threshold``: a confidence below ``settings.relevance_threshold`` collapses
``label`` to ``NOT_RELEVANT`` and ``matched_item_id`` to ``None``.
"""

from __future__ import annotations

import re
import time

from .config import SETTINGS, Settings
from .models import Classification, Label

# --- Anthropic rate-limit / overload backoff (SPEC §7 resilience) ----------
# Retry transient capacity errors (HTTP 429 too-many-requests, 529 overloaded,
# 5xx) with exponential backoff, then surface a clean error once exhausted.
_RETRY_STATUS = frozenset({429, 500, 502, 503, 529})
_RETRY_EXC_NAMES = frozenset({
    "RateLimitError", "OverloadedError", "InternalServerError",
    "APITimeoutError", "APIConnectionError",
})
_MAX_RETRIES = 5        # total attempts before giving up
_BASE_BACKOFF = 0.5     # seconds; delay = _BASE_BACKOFF * 2**attempt

# Tool that forces structured JSON output on the real Anthropic path (SPEC §7).
_CLASSIFY_TOOL = {
    "name": "record_classification",
    "description": (
        "Record the single most important relationship between the lab profile "
        "and the new paper as strict structured data."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "label": {
                "type": "string",
                "enum": ["ANSWERS", "CONTRADICTS", "EXTENDS", "NOT_RELEVANT"],
            },
            "reason": {
                "type": "string",
                "description": "One sentence on why it matters to THIS lab, naming the matched item.",
            },
            "matched_item_id": {
                "type": ["string", "null"],
                "description": "Profile item id, or null if NOT_RELEVANT.",
            },
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        },
        "required": ["label", "reason", "matched_item_id", "confidence"],
        "additionalProperties": False,
    },
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Lexical cues that bias the degraded classifier toward a relationship label.
_CONTRADICT_CUES = ("contradict", "challenge", "refute", "no effect", "fails", "unlike", "contrary")
_ANSWER_CUES = ("answer", "demonstrate", "confirm", "establish", "resolve", "show that")
_EXTEND_CUES = ("extend", "further", "additional", "novel", "expand", "build on", "moreover")


def _apply_threshold(c: Classification, settings: Settings) -> Classification:
    """Collapse low-confidence results to NOT_RELEVANT (SPEC §7).

    Applied to BOTH the real and degraded paths so the threshold rule lives in
    exactly one place.
    """
    if c.confidence < settings.relevance_threshold:
        return Classification(
            label=Label.NOT_RELEVANT,
            reason=c.reason,
            matched_item_id=None,
            confidence=c.confidence,
        )
    return c


def _anthropic_client(settings: Settings):
    """Lazily build an Anthropic client (degraded-safe; no import at module load)."""
    from anthropic import Anthropic  # noqa: PLC0415

    return Anthropic(api_key=settings.anthropic_api_key)


def _is_retryable(exc: Exception) -> bool:
    """True for transient Anthropic errors worth retrying (429 / overload / 5xx).

    Detection is duck-typed on ``status_code`` and the exception class name so it
    works without importing the anthropic SDK and stays easy to simulate in tests.
    """
    status = getattr(exc, "status_code", None)
    if status in _RETRY_STATUS:
        return True
    return type(exc).__name__ in _RETRY_EXC_NAMES


def _create_with_backoff(client, **kwargs):
    """Call ``client.messages.create`` with exponential backoff on rate limits.

    Retries only transient capacity errors (see ``_is_retryable``); any other
    error propagates immediately. After ``_MAX_RETRIES`` exhausted attempts a
    clean ``RuntimeError`` is raised instead of leaking the raw SDK exception.
    """
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 — re-raise non-retryable below
            if not _is_retryable(exc):
                raise
            last_exc = exc
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_BASE_BACKOFF * (2 ** attempt))
    raise RuntimeError(
        f"Anthropic classification failed after {_MAX_RETRIES} attempts "
        f"(rate limit / overload): {last_exc}"
    ) from last_exc


def _classify_real(system: str, user: str, settings: Settings) -> Classification:
    """Real Anthropic path: JSON enforced via forced tool use, with rate-limit
    backoff around the API call."""
    client = _anthropic_client(settings)
    response = _create_with_backoff(
        client,
        model=settings.reason_model,
        max_tokens=1024,
        system=system,
        tools=[_CLASSIFY_TOOL],
        tool_choice={"type": "tool", "name": _CLASSIFY_TOOL["name"]},
        messages=[{"role": "user", "content": user}],
    )
    tool_use = next(b for b in response.content if b.type == "tool_use")
    return Classification(**tool_use.input)


# --- deterministic degraded path -------------------------------------------

_ITEM_LINE_RE = re.compile(r"^- \[(?P<id>[^\s]+) · (?P<kind>[^\]]+)\] (?P<text>.+)$")


def _parse_user_prompt(user: str) -> tuple[list[tuple[str, str]], str]:
    """Recover (item_id, item_text) pairs and the paper text from the user prompt.

    The degraded classifier has no profile object — it reconstructs the items from
    the rendered prompt produced by ``prompts.build_prompt`` so the stand-in can
    still match against the real retrieved items.
    """
    items: list[tuple[str, str]] = []
    paper_parts: list[str] = []
    in_paper = False
    in_prior = False
    for line in user.splitlines():
        # The optional PRIOR WORK section (opt-in vector prior-work) sits between
        # LAB PROFILE and NEW PAPER; skip it so it pollutes neither the recovered
        # profile items nor the paper text.
        if line.startswith("PRIOR WORK:"):
            in_prior = True
            continue
        if line.startswith("NEW PAPER:"):
            in_paper = True
            in_prior = False
            continue
        if line.startswith("Return strict JSON only:"):
            break
        if in_prior:
            continue
        m = _ITEM_LINE_RE.match(line)
        if m and not in_paper:
            items.append((m.group("id"), m.group("text")))
        elif in_paper:
            paper_parts.append(line)
    return items, " ".join(paper_parts)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


def _classify_degraded(user: str, settings: Settings) -> Classification:
    """Deterministic rule-based stand-in (no Anthropic key).

    Picks the best-matching profile item by lexical token overlap with the paper,
    infers a label from lexical cues, and sets confidence from overlap strength.
    """
    items, paper = _parse_user_prompt(user)
    paper_tokens = _tokens(paper)

    best_id: str | None = None
    best_overlap = 0.0
    for item_id, item_text in items:
        item_tokens = _tokens(item_text)
        if not item_tokens or not paper_tokens:
            continue
        # Asymmetric recall: fraction of profile-item tokens found in the paper.
        # Symmetric Jaccard penalises long abstracts unfairly; this asks "how much
        # of the profile item does the paper cover?" which is what we care about.
        overlap = len(item_tokens & paper_tokens) / len(item_tokens)
        if overlap > best_overlap:
            best_overlap = overlap
            best_id = item_id

    # Confidence directly equals the recall score; cap below 1.0.
    confidence = round(min(best_overlap, 0.95), 3)

    paper_lc = paper.lower()
    if any(cue in paper_lc for cue in _CONTRADICT_CUES):
        label = Label.CONTRADICTS
    elif any(cue in paper_lc for cue in _ANSWER_CUES):
        label = Label.ANSWERS
    elif any(cue in paper_lc for cue in _EXTEND_CUES):
        label = Label.EXTENDS
    else:
        label = Label.EXTENDS  # default relationship when relevant but uncued

    reason = (
        f"[deterministic stand-in] Best lexical match is profile item "
        f"{best_id or 'none'} (overlap {best_overlap:.2f})."
    )
    return Classification(
        label=label, reason=reason, matched_item_id=best_id, confidence=confidence
    )


def classify(system: str, user: str, settings: Settings = SETTINGS) -> Classification:
    """Call Claude with the given prompt and return a parsed Classification.

    Real Anthropic (JSON-enforced via tool use) when a key is present; deterministic
    fallback otherwise. The threshold-collapse rule is applied to both paths.
    """
    if settings.anthropic_api_key:
        result = _classify_real(system, user, settings)
    else:
        result = _classify_degraded(user, settings)
    return _apply_threshold(result, settings)
