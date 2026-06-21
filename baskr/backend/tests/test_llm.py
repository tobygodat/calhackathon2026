"""Phase 2 — llm.classify: schema-valid Classification + threshold collapse.

Default path is the deterministic fallback (no Anthropic key). The threshold rule
is exercised directly via monkeypatch of the inner classifier.
"""

from __future__ import annotations

from app import llm
from app.config import Settings
from app.models import Classification, Label
from app.prompts import build_prompt
from app.models import PaperOut, ProfileItem, ProfileItemKind

_SETTINGS = Settings(anthropic_api_key=None, relevance_threshold=0.5)


def _prompt() -> tuple[str, str]:
    items = [
        ProfileItem(id="oq_1", kind=ProfileItemKind.OPEN_QUESTION,
                    text="Does butyrate modulate gut inflammation in colitis?"),
        ProfileItem(id="fnd_1", kind=ProfileItemKind.FINDING,
                    text="SCFAs support regulatory T cell differentiation."),
    ]
    paper = PaperOut(
        source="pubmed", source_id="1",
        title="Butyrate confirms Treg induction in colitis",
        abstract="We demonstrate butyrate modulates gut inflammation and induces Tregs.",
    )
    return build_prompt(items, paper)


def test_classify_returns_valid_classification() -> None:
    system, user = _prompt()
    result = llm.classify(system, user, _SETTINGS)
    assert isinstance(result, Classification)  # pydantic-validated on construction
    assert isinstance(result.label, Label)


def test_label_is_always_valid_enum() -> None:
    system, user = _prompt()
    result = llm.classify(system, user, _SETTINGS)
    assert result.label in set(Label)


def test_low_confidence_collapses_to_not_relevant(monkeypatch) -> None:
    """A forced low-confidence result must collapse to NOT_RELEVANT / matched=None."""
    forced = Classification(
        label=Label.ANSWERS,
        reason="forced high-relevance label but low confidence",
        matched_item_id="oq_1",
        confidence=0.10,  # below threshold 0.5
    )
    monkeypatch.setattr(llm, "_classify_degraded", lambda user, settings: forced)

    system, user = _prompt()
    result = llm.classify(system, user, _SETTINGS)
    assert result.label is Label.NOT_RELEVANT
    assert result.matched_item_id is None
    assert result.confidence == 0.10  # confidence itself is preserved


def test_high_confidence_is_preserved(monkeypatch) -> None:
    forced = Classification(
        label=Label.CONTRADICTS,
        reason="strong match",
        matched_item_id="fnd_1",
        confidence=0.88,
    )
    monkeypatch.setattr(llm, "_classify_degraded", lambda user, settings: forced)

    system, user = _prompt()
    result = llm.classify(system, user, _SETTINGS)
    assert result.label is Label.CONTRADICTS
    assert result.matched_item_id == "fnd_1"
    assert result.confidence == 0.88


def test_degraded_path_matches_a_profile_item() -> None:
    """Deterministic stand-in should pick a matched_item_id from the prompt items."""
    system, user = _prompt()
    # Force confidence above threshold path by checking the raw degraded output.
    raw = llm._classify_degraded(user, _SETTINGS)
    assert raw.matched_item_id in {"oq_1", "fnd_1"}


def test_degraded_sets_new_memory_when_matched() -> None:
    """The 'Remember' step: a matched degraded result proposes a new_memory."""
    system, user = _prompt()
    raw = llm._classify_degraded(user, _SETTINGS)
    assert raw.matched_item_id is not None
    assert raw.new_memory is not None
    assert raw.matched_item_id in raw.new_memory


def test_threshold_collapse_drops_new_memory(monkeypatch) -> None:
    """A sub-threshold (NOT_RELEVANT) result must not carry a new_memory."""
    forced = Classification(
        label=Label.ANSWERS,
        reason="forced",
        matched_item_id="oq_1",
        confidence=0.10,  # below threshold 0.5
        new_memory="should be dropped on collapse",
    )
    monkeypatch.setattr(llm, "_classify_degraded", lambda user, settings: forced)

    system, user = _prompt()
    result = llm.classify(system, user, _SETTINGS)
    assert result.label is Label.NOT_RELEVANT
    assert result.new_memory is None


def test_high_confidence_preserves_new_memory(monkeypatch) -> None:
    """A relevant result keeps the proposed new_memory for write-back."""
    forced = Classification(
        label=Label.EXTENDS,
        reason="strong match",
        matched_item_id="fnd_1",
        confidence=0.80,
        new_memory="Butyrate extends the SCFA/Treg finding.",
    )
    monkeypatch.setattr(llm, "_classify_degraded", lambda user, settings: forced)

    system, user = _prompt()
    result = llm.classify(system, user, _SETTINGS)
    assert result.new_memory == "Butyrate extends the SCFA/Treg finding."
