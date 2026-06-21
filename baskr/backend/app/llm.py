"""Anthropic Claude client with JSON-enforced output (SPEC §7).

Sends the system+user prompt from ``prompts.build_prompt`` and parses a strict
``Classification``. JSON output should be enforced via tool use or response_format;
confidence below ``Settings.relevance_threshold`` collapses to NOT_RELEVANT.

Model id is read from ``Settings.reason_model`` — confirm the recommended current
claude-* model at build time (SPEC §4) rather than hardcoding.
"""

from __future__ import annotations

from .config import SETTINGS, Settings
from .models import Classification


def classify(system: str, user: str, settings: Settings = SETTINGS) -> Classification:
    """Call Claude with the given prompt and return a parsed Classification."""
    raise NotImplementedError
