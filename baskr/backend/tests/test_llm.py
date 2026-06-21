"""Phase 2 — llm.classify: schema-valid Classification + threshold collapse.

Default path is the deterministic fallback (no Anthropic key). The threshold rule
is exercised directly via monkeypatch of the inner classifier.
"""

from __future__ import annotations

import pytest

from app import llm
from app.config import Settings
from app.models import Classification, Label
from app.prompts import build_prompt
from app.models import PaperOut, ProfileItem, ProfileItemKind

_SETTINGS = Settings(anthropic_api_key=None, relevance_threshold=0.5)
_LIVE_SETTINGS = Settings(
    anthropic_api_key="sk-ant-test",
    relevance_threshold=0.5,
    reason_model="claude-sonnet-4-6",
)


def _tool_response():
    """A fake Anthropic Messages response carrying one forced tool_use block."""
    class _ToolBlock:
        type = "tool_use"
        input = {
            "label": "ANSWERS", "reason": "ok",
            "matched_item_id": "oq_1", "confidence": 0.9,
        }

    class _Resp:
        content = [_ToolBlock()]

    return _Resp()


def _fake_client(create):
    """Build a stand-in Anthropic client whose messages.create == ``create``."""
    class _Msgs:
        pass

    _Msgs.create = staticmethod(create)

    class _Client:
        messages = _Msgs()

    return _Client()


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


# --- rate-limit / overload backoff (ARCHITECTURE_DECISIONS.md #12) ----------

def test_classify_retries_on_rate_limit(monkeypatch) -> None:
    """A simulated 429 is retried with exponential backoff, then succeeds."""
    class _Fake429(Exception):
        status_code = 429

    calls = [0]

    def create(**kwargs):
        calls[0] += 1
        if calls[0] < 3:        # fail the first two attempts
            raise _Fake429("rate limited")
        return _tool_response()

    sleeps: list[float] = []
    monkeypatch.setattr(llm, "_anthropic_client", lambda s: _fake_client(create))
    monkeypatch.setattr(llm, "_BASE_BACKOFF", 0.0)          # no real waiting
    monkeypatch.setattr(llm.time, "sleep", lambda d: sleeps.append(d))

    system, user = _prompt()
    result = llm.classify(system, user, _LIVE_SETTINGS)

    assert isinstance(result, Classification)
    assert result.label is Label.ANSWERS
    assert calls[0] == 3            # two failures + one success
    assert len(sleeps) == 2         # one backoff per retried failure


def test_classify_raises_clean_error_after_exhaustion(monkeypatch) -> None:
    """Persistent overload (529) exhausts retries and surfaces a clean RuntimeError."""
    class _Fake529(Exception):
        status_code = 529

    calls = [0]

    def create(**kwargs):
        calls[0] += 1
        raise _Fake529("overloaded")

    monkeypatch.setattr(llm, "_anthropic_client", lambda s: _fake_client(create))
    monkeypatch.setattr(llm, "_BASE_BACKOFF", 0.0)
    monkeypatch.setattr(llm.time, "sleep", lambda d: None)

    system, user = _prompt()
    with pytest.raises(RuntimeError, match="after .* attempts"):
        llm.classify(system, user, _LIVE_SETTINGS)
    assert calls[0] == llm._MAX_RETRIES   # tried exactly the capped number of times


def test_classify_does_not_retry_non_retryable(monkeypatch) -> None:
    """A 400 (bad request) is not retried — it propagates on the first attempt."""
    class _BadRequest(Exception):
        status_code = 400

    calls = [0]

    def create(**kwargs):
        calls[0] += 1
        raise _BadRequest("bad request")

    monkeypatch.setattr(llm, "_anthropic_client", lambda s: _fake_client(create))
    monkeypatch.setattr(llm.time, "sleep", lambda d: None)

    system, user = _prompt()
    with pytest.raises(_BadRequest):
        llm.classify(system, user, _LIVE_SETTINGS)
    assert calls[0] == 1                   # no retries
