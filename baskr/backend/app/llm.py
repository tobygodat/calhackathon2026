"""Anthropic Claude client with JSON-enforced output (SPEC §7).

Sends the system+user prompt from ``prompts.build_prompt`` and parses a strict
``Classification``. Confidence below ``Settings.relevance_threshold`` collapses
to NOT_RELEVANT.

Model id is read from ``Settings.reason_model`` (defaults to claude-sonnet-4-6).
"""

from __future__ import annotations

import json

from .config import SETTINGS, Settings
from .models import Classification, Label

_DEFAULT_MODEL = "claude-sonnet-4-6"


def classify(system: str, user: str, settings: Settings = SETTINGS) -> Classification:
    """Call Claude with the given prompt and return a parsed Classification."""
    from anthropic import Anthropic

    model = settings.reason_model or _DEFAULT_MODEL
    client = Anthropic(api_key=settings.anthropic_api_key)

    message = client.messages.create(
        model=model,
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    raw_text = message.content[0].text.strip()

    # Strip markdown code fences if Claude wraps the JSON
    if raw_text.startswith("```"):
        lines = raw_text.split("\n")
        # Drop first and last fence lines
        inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        raw_text = "\n".join(inner).strip()

    data = json.loads(raw_text)
    classification = Classification(
        label=Label(data["label"]),
        reason=data.get("reason", ""),
        matched_item_id=data.get("matched_item_id"),
        confidence=float(data.get("confidence", 0.0)),
    )

    # Collapse low-confidence results to NOT_RELEVANT
    if classification.confidence < settings.relevance_threshold:
        classification = Classification(
            label=Label.NOT_RELEVANT,
            reason=classification.reason,
            matched_item_id=classification.matched_item_id,
            confidence=classification.confidence,
        )

    return classification
