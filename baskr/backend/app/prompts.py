"""Prompt construction for the classification engine (SPEC §7).

``build_prompt`` renders the retrieved profile items + one paper into the
(system, user) pair Claude scores. The user message must request strict JSON:
{label, reason, matched_item_id, confidence}.
"""

from __future__ import annotations

from typing import Any

from .models import PaperOut, ProfileItem

SYSTEM_PROMPT = (
    "You are Baskr, a research-watch agent for a gut microbiome lab. Given the "
    "lab's context profile and one new paper abstract, decide the single most "
    "important relationship between them. Be discerning — most papers are "
    "NOT_RELEVANT."
)


# Strict-JSON instruction block (SPEC §7). Kept as a module constant so tests can
# assert the contract keys are present verbatim.
_JSON_INSTRUCTION = (
    "Return strict JSON only:\n"
    "{\n"
    '  "label": "ANSWERS|CONTRADICTS|EXTENDS|NOT_RELEVANT",\n'
    '  "reason": "<one sentence why it matters to THIS lab, naming the matched item>",\n'
    '  "matched_item_id": "<profile item id, or null if NOT_RELEVANT>",\n'
    '  "confidence": <0.0-1.0>\n'
    "}"
)


def _prior_work_text(record: Any) -> tuple[str, str]:
    """Pull a (title, abstract) pair from a prior-work record (dict or model)."""
    if isinstance(record, dict):
        return str(record.get("title", "") or ""), str(record.get("abstract", "") or "")
    return str(getattr(record, "title", "") or ""), str(getattr(record, "abstract", "") or "")


def _render_prior_work(prior_work: list[Any]) -> str:
    """Render prior-work records as one ``- {title} — {abstract snippet}`` line each.

    Lines deliberately omit the ``[id · kind]`` bracket form so they can never be
    mistaken for LAB PROFILE items by ``llm._parse_user_prompt`` (which also skips
    the whole PRIOR WORK block explicitly)."""
    lines = []
    for rec in prior_work:
        title, abstract = _prior_work_text(rec)
        snippet = abstract.strip().replace("\n", " ")
        if len(snippet) > 240:
            snippet = snippet[:240].rstrip() + "…"
        line = f"- {title}".rstrip()
        if snippet:
            line = f"{line} — {snippet}" if title else f"- {snippet}"
        lines.append(line)
    return "\n".join(lines)


def build_prompt(items: list[ProfileItem], paper: PaperOut,
                 prior_work: list[Any] | None = None) -> tuple[str, str]:
    """Return ``(system, user)`` messages for ``llm.classify`` (SPEC §7).

    Deterministic and side-effect-free. ``system`` is ``SYSTEM_PROMPT`` verbatim;
    ``user`` lists each retrieved profile item as ``- [{id} · {kind}] {text}``,
    then — when ``prior_work`` is supplied (opt-in agent-loop step 3) — a
    ``PRIOR WORK`` section of similar prior papers, then the paper title +
    abstract, then the strict-JSON contract block. When ``prior_work`` is None or
    empty the output is byte-for-byte identical to the no-prior-work form.
    """
    item_lines = "\n".join(
        f"- [{it.id} · {it.kind.value}] {it.text}" for it in items
    )

    prior_block = ""
    if prior_work:
        prior_block = (
            "PRIOR WORK:\n"
            f"{_render_prior_work(prior_work)}\n\n"
        )

    user = (
        "LAB PROFILE:\n"
        f"{item_lines}\n\n"
        f"{prior_block}"
        "NEW PAPER:\n"
        f"Title: {paper.title}\n"
        f"Abstract: {paper.abstract}\n\n"
        f"{_JSON_INSTRUCTION}"
    )
    return SYSTEM_PROMPT, user
