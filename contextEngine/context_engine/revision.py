"""Belief revision: how the user context *changes its mind*.

When the user reviews an incoming claim that contradicts something in their
context and **accepts** it, the context must change by an amount proportional to
how much the new claim overturns the old belief — "the Earth is slightly
egg-shaped" nudges a belief; "the Earth is square" replaces it.

The magnitude comes from two signals, deliberately kept separate because they
measure different things:

- **relatedness** — local cosine between the incoming claim and the candidate
  belief. Embeddings measure *aboutness*, so this only tells us *which* belief is
  under attack, not how wrong it now is. ("egg-shaped", "round", "square" all sit
  near each other.)
- **severity** — an LLM (or heuristic) judgment of how much accepting the claim
  overturns the belief, 0..1. This is the real magnitude knob.

Severity selects the revision mode:

    severity < 0.30   merge      revise the belief in place (same id, version++)
    0.30..0.70        fork       keep both; mark the old belief contested
    >= 0.70           supersede  retire the old belief; the new one replaces it

A claim that doesn't actually contradict anything is just inserted.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .config import SETTINGS, Settings
from .embeddings import embed_text
from .models import ContextItem, ItemKind

# Severity thresholds between revision modes (tunable).
_MERGE_MAX = 0.30
_SUPERSEDE_MIN = 0.70
# Below this relatedness the incoming claim isn't really about the candidate, so
# there is nothing to contradict — we just insert it.
_RELATEDNESS_GATE = 0.20


@dataclass
class RevisionProposal:
    incoming: ContextItem
    target: ContextItem | None        # the belief most under attack, if any
    relatedness: float                # local cosine to the target, 0..1
    stance: str                       # CONTRADICTS | EXTENDS | ANSWERS | NOT_RELEVANT
    severity: float                   # 0..1 — how much accepting overturns target
    mode: str                         # insert | merge | fork | supersede
    revised_text: str                 # proposed belief text after revision
    rationale: str
    used_real_model: bool = False
    applied: bool = False
    changes: list[str] = field(default_factory=list)  # human-readable log

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "stance": self.stance,
            "severity": round(self.severity, 3),
            "relatedness": round(self.relatedness, 3),
            "rationale": self.rationale,
            "used_real_model": self.used_real_model,
            "applied": self.applied,
            "changes": self.changes,
            "incoming": self.incoming.to_dict(),
            "target": self.target.to_dict() if self.target else None,
            "revised_text": self.revised_text,
        }


# --- LLM judge (forced tool use) + heuristic fallback ----------------------

_JUDGE_TOOL = {
    "name": "judge_revision",
    "description": "Judge how an accepted incoming claim revises an existing belief.",
    "input_schema": {
        "type": "object",
        "properties": {
            "stance": {
                "type": "string",
                "enum": ["CONTRADICTS", "EXTENDS", "ANSWERS", "NOT_RELEVANT"],
                "description": "The incoming claim's relationship to the existing belief.",
            },
            "severity": {
                "type": "number", "minimum": 0.0, "maximum": 1.0,
                "description": (
                    "If CONTRADICTS: how much accepting the claim overturns the "
                    "belief. ~0.1 = adds a small qualifier; ~0.5 = materially "
                    "limits it; ~0.9 = negates its core. 0 for non-contradictions."
                ),
            },
            "revised_text": {
                "type": "string",
                "description": (
                    "The belief rewritten to reflect the accepted claim: a merged, "
                    "more nuanced sentence for small severity; the new claim itself "
                    "for high severity."
                ),
            },
            "rationale": {"type": "string"},
        },
        "required": ["stance", "severity", "revised_text", "rationale"],
        "additionalProperties": False,
    },
}

_NEGATION_CUES = (
    "not ", "no ", "fails", "cannot", "does not", "doesn't", "contrary",
    "contradict", "refute", "disprove", "incorrect", "wrong", "actually",
    "instead", "rather than", "overturn", "reject",
)
# Hedges signal a *qualification* of the belief (small severity) — "the Earth is
# slightly egg-shaped" keeps the belief mostly intact.
_HEDGE_CUES = (
    "slightly", "approximately", "roughly", "mostly", "largely", "nearly",
    "somewhat", "a bit", "to some extent", "not perfectly", "not exactly",
    "minor", "subtle", "marginally", "in part", "partially",
)
# Flat reversals signal the belief's core is wrong (large severity) — "the Earth
# is actually square" overturns it.
_REVERSAL_CUES = (
    "at all", "actually", "completely", "entirely", "no longer", "wrong",
    "incorrect", "disprove", "refute", "the opposite", "nothing like",
    "fundamentally", "in fact not",
)


def _judge_real(incoming: ContextItem, target: ContextItem, settings: Settings) -> dict:
    from anthropic import Anthropic

    client = Anthropic(api_key=settings.anthropic_api_key)
    user = (
        "EXISTING BELIEF (the user currently holds this):\n"
        f"  {target.text}\n\n"
        "INCOMING CLAIM (the user just reviewed and ACCEPTED this):\n"
        f"  {incoming.text}\n\n"
        "Judge the relationship and, if it contradicts the belief, how much "
        "accepting it overturns the belief."
    )
    resp = client.messages.create(
        model=settings.extract_model,
        max_tokens=1024,
        system=(
            "You maintain a researcher's evolving beliefs. Judge how an accepted "
            "claim should revise an existing belief, scaling the change to how "
            "much the claim actually overturns it."
        ),
        tools=[_JUDGE_TOOL],
        tool_choice={"type": "tool", "name": _JUDGE_TOOL["name"]},
        messages=[{"role": "user", "content": user}],
    )
    tool_use = next(b for b in resp.content if b.type == "tool_use")
    return tool_use.input


def _judge_degraded(
    incoming: ContextItem, target: ContextItem, relatedness: float
) -> dict:
    """Heuristic stand-in: infer contradiction + severity from cues and distance.

    Severity rises with negation cues in the incoming claim and with how *far* the
    two sit apart given that they're about the same thing (1 - relatedness), so a
    same-topic claim that reads as a reversal scores high.
    """
    inc_lc = incoming.text.lower()
    has_negation = any(c in inc_lc for c in _NEGATION_CUES)
    if not has_negation:
        return {
            "stance": "EXTENDS",
            "severity": 0.0,
            "revised_text": incoming.text,
            "rationale": "[heuristic] no contradiction cue; treated as additive.",
        }
    # Base severity rises as the claim sits *further* from the belief it's about.
    severity = 0.4 + (1.0 - relatedness) * 0.4
    # Language is a stronger signal than keyless cosine: a hedge pins it low (a
    # qualification), a flat reversal pins it high (the core is wrong).
    if any(c in inc_lc for c in _HEDGE_CUES):
        severity = min(severity, _MERGE_MAX - 0.05)
    if any(c in inc_lc for c in _REVERSAL_CUES):
        severity = max(severity, _SUPERSEDE_MIN + 0.05)
    severity = round(min(0.95, max(0.05, severity)), 3)

    revised = (f"{target.text} However, {incoming.text}"
               if severity < _MERGE_MAX else incoming.text)
    return {
        "stance": "CONTRADICTS",
        "severity": severity,
        "revised_text": revised,
        "rationale": (f"[heuristic] negation cue; "
                      f"{'hedge' if severity < _MERGE_MAX else 'reversal' if severity >= _SUPERSEDE_MIN else 'partial'}"
                      f" language; relatedness {relatedness:.2f}."),
    }


def _mode_for(stance: str, severity: float, relatedness: float) -> str:
    if stance != "CONTRADICTS" or relatedness < _RELATEDNESS_GATE:
        return "insert"
    if severity < _MERGE_MAX:
        return "merge"
    if severity >= _SUPERSEDE_MIN:
        return "supersede"
    return "fork"


def assess(engine, incoming: ContextItem, settings: Settings = SETTINGS) -> RevisionProposal:
    """Decide what accepting ``incoming`` would do, without mutating the store."""
    # Find the active belief this claim is most about (same kind first).
    hits = engine.search(incoming.text, top_k=1, kind=incoming.kind)
    if not hits:
        hits = engine.search(incoming.text, top_k=1)
    target = hits[0].item if hits else None
    relatedness = hits[0].score if hits else 0.0

    if target is None:
        return RevisionProposal(
            incoming=incoming, target=None, relatedness=0.0, stance="NOT_RELEVANT",
            severity=0.0, mode="insert", revised_text=incoming.text,
            rationale="No existing belief to compare against.", used_real_model=False,
        )

    used_real = bool(settings.anthropic_api_key)
    if used_real:
        try:
            j = _judge_real(incoming, target, settings)
        except Exception:  # noqa: BLE001 - degrade rather than fail the accept
            j = _judge_degraded(incoming, target, relatedness)
            used_real = False
    else:
        j = _judge_degraded(incoming, target, relatedness)

    stance = j.get("stance", "NOT_RELEVANT")
    severity = float(j.get("severity", 0.0) or 0.0)
    mode = _mode_for(stance, severity, relatedness)
    return RevisionProposal(
        incoming=incoming, target=target, relatedness=relatedness, stance=stance,
        severity=severity, mode=mode,
        revised_text=j.get("revised_text", incoming.text) or incoming.text,
        rationale=j.get("rationale", ""), used_real_model=used_real,
    )


def _stamp(item: ContextItem, note: str) -> None:
    item.provenance.append(f"{time.strftime('%Y-%m-%d')} · {note}")


def apply(engine, p: RevisionProposal, settings: Settings = SETTINGS) -> RevisionProposal:
    """Mutate the store according to the proposal's mode. Idempotent per call."""
    store = engine.store

    if p.mode == "insert":
        p.incoming.embedding = embed_text(p.incoming.embed_text(), settings)
        _stamp(p.incoming, "added as new belief (no conflict)")
        store.add([p.incoming])
        p.changes.append(f"inserted new {p.incoming.kind.value} {p.incoming.id}")

    elif p.mode == "merge":
        # Revise the belief in place: same id, bumped version, nuanced text.
        target = p.target
        target.text = p.revised_text
        target.version += 1
        target.confidence = max(target.confidence, p.incoming.confidence)
        _stamp(target, f"merged contradiction (severity {p.severity:.2f}) "
                       f"from {p.incoming.source_id or 'review'}")
        target.embedding = embed_text(target.embed_text(), settings)
        store.update(target)
        p.changes.append(f"merged into {target.id} -> v{target.version}")

    elif p.mode == "fork":
        # Keep both; the old belief becomes contested, the new one links to it.
        target = p.target
        target.status = "contested"
        _stamp(target, f"contested by incoming claim (severity {p.severity:.2f})")
        store.update(target)
        p.incoming.supersedes = None
        _stamp(p.incoming, f"forks contested belief {target.id}")
        p.incoming.embedding = embed_text(p.incoming.embed_text(), settings)
        store.add([p.incoming])
        p.changes.append(f"forked: {target.id} -> contested; added {p.incoming.id}")

    elif p.mode == "supersede":
        # Retire the old belief (kept as history) and install the new one.
        target = p.target
        target.status = "superseded"
        _stamp(target, f"superseded (severity {p.severity:.2f})")
        store.update(target)
        p.incoming.text = p.revised_text
        p.incoming.supersedes = target.id
        p.incoming.version = target.version + 1
        _stamp(p.incoming, f"supersedes {target.id}")
        p.incoming.embedding = embed_text(p.incoming.embed_text(), settings)
        store.add([p.incoming])
        p.changes.append(f"superseded {target.id}; installed {p.incoming.id}")

    p.applied = True
    return p


def reconcile(
    engine, incoming: ContextItem, *, auto_apply: bool = True,
    settings: Settings = SETTINGS,
) -> RevisionProposal:
    """Assess and (by default) apply the revision for an accepted incoming claim."""
    proposal = assess(engine, incoming, settings)
    if auto_apply:
        apply(engine, proposal, settings)
    return proposal
