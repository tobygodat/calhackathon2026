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


def build_prompt(items: list[ProfileItem], paper: PaperOut) -> tuple[str, str]:
    """Return ``(system, user)`` messages for ``llm.classify`` (SPEC §7)."""
    if items:
        items_text = "\n".join(
            f"[{item.kind.value.upper()}] (id={item.id}) {item.text}"
            for item in items
        )
    else:
        items_text = "(no profile items)"

    user = (
        "LAB PROFILE ITEMS:\n"
        f"{items_text}\n\n"
        "NEW PAPER:\n"
        f"Title: {paper.title}\n"
        f"Abstract: {paper.abstract or '(no abstract available)'}\n\n"
        "Classify this paper relative to the lab profile. "
        "Respond ONLY with valid JSON — no markdown, no extra text — matching exactly:\n"
        '{"label": "ANSWERS|CONTRADICTS|EXTENDS|NOT_RELEVANT|SCOOP", '
        '"reason": "<one concise sentence>", '
        '"matched_item_id": "<profile item id or null>", '
        '"confidence": <float between 0.0 and 1.0>}'
    )
    return SYSTEM_PROMPT, user
