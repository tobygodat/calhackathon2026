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
    raise NotImplementedError
