"""Prompt construction for the classification engine (SPEC §7).

``build_prompt`` renders the retrieved profile items + one paper into the
(system, user) pair Claude scores. The user message must request strict JSON:
{label, reason, matched_item_id, confidence}.
"""

from __future__ import annotations

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


def build_prompt(items: list[ProfileItem], paper: PaperOut) -> tuple[str, str]:
    """Return ``(system, user)`` messages for ``llm.classify`` (SPEC §7).

    Deterministic and side-effect-free. ``system`` is ``SYSTEM_PROMPT`` verbatim;
    ``user`` lists each retrieved profile item as ``- [{id} · {kind}] {text}``,
    then the paper title + abstract, then the strict-JSON contract block.
    """
    item_lines = "\n".join(
        f"- [{it.id} · {it.kind.value}] {it.text}" for it in items
    )

    user = (
        "LAB PROFILE:\n"
        f"{item_lines}\n\n"
        "NEW PAPER:\n"
        f"Title: {paper.title}\n"
        f"Abstract: {paper.abstract}\n\n"
        f"{_JSON_INSTRUCTION}"
    )
    return SYSTEM_PROMPT, user
