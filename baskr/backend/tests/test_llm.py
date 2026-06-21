"""Unit tests for the Anthropic Claude LLM wrapper (app/llm.py).

Note: classify() imports Anthropic lazily inside the function body,
so we must patch ``anthropic.Anthropic`` (the source), not ``app.llm.Anthropic``.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.llm import classify
from app.models import Classification, Label


def _make_anthropic_response(json_payload: dict) -> MagicMock:
    """Build a mock Anthropic messages.create response."""
    mock_resp = MagicMock()
    content_block = MagicMock()
    content_block.text = json.dumps(json_payload)
    mock_resp.content = [content_block]
    return mock_resp


def _make_anthropic_response_text(text: str) -> MagicMock:
    mock_resp = MagicMock()
    content_block = MagicMock()
    content_block.text = text
    mock_resp.content = [content_block]
    return mock_resp


class TestClassify:
    def test_returns_classification(self, settings):
        payload = {
            "label": "ANSWERS",
            "reason": "Directly answers the open question.",
            "matched_item_id": "oq_1",
            "confidence": 0.85,
        }
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = (
                _make_anthropic_response(payload)
            )
            result = classify("system", "user", settings=settings)
        assert isinstance(result, Classification)
        assert result.label == Label.ANSWERS
        assert result.confidence == 0.85
        assert result.matched_item_id == "oq_1"

    def test_label_not_relevant_returned_unchanged(self, settings):
        """A NOT_RELEVANT label above threshold stays NOT_RELEVANT."""
        payload = {
            "label": "NOT_RELEVANT",
            "reason": "Unrelated to microbiome.",
            "matched_item_id": None,
            "confidence": 0.9,
        }
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = (
                _make_anthropic_response(payload)
            )
            result = classify("system", "user", settings=settings)
        assert result.label == Label.NOT_RELEVANT

    def test_low_confidence_collapses_to_not_relevant(self, settings):
        """Confidence below threshold (0.5) must collapse to NOT_RELEVANT."""
        payload = {
            "label": "EXTENDS",
            "reason": "Weak extension.",
            "matched_item_id": "fnd_1",
            "confidence": 0.3,  # below settings.relevance_threshold = 0.5
        }
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = (
                _make_anthropic_response(payload)
            )
            result = classify("system", "user", settings=settings)
        assert result.label == Label.NOT_RELEVANT
        assert result.confidence == 0.3  # original confidence preserved

    def test_exactly_at_threshold_stays(self, settings):
        """Confidence exactly at threshold (0.5) should NOT collapse."""
        payload = {
            "label": "EXTENDS",
            "reason": "Borderline.",
            "matched_item_id": None,
            "confidence": 0.5,
        }
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = (
                _make_anthropic_response(payload)
            )
            result = classify("system", "user", settings=settings)
        assert result.label == Label.EXTENDS

    def test_strips_markdown_fences(self, settings):
        """Claude sometimes wraps JSON in ```json ... ``` fences."""
        inner = json.dumps({
            "label": "CONTRADICTS",
            "reason": "Contradicts assumption.",
            "matched_item_id": "asm_1",
            "confidence": 0.7,
        })
        fenced = f"```json\n{inner}\n```"
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = (
                _make_anthropic_response_text(fenced)
            )
            result = classify("system", "user", settings=settings)
        assert result.label == Label.CONTRADICTS

    def test_uses_settings_model(self, settings):
        payload = {
            "label": "EXTENDS",
            "reason": "x",
            "matched_item_id": None,
            "confidence": 0.6,
        }
        with patch("anthropic.Anthropic") as MockAnthropic:
            mock_client = MockAnthropic.return_value
            mock_client.messages.create.return_value = (
                _make_anthropic_response(payload)
            )
            classify("system", "user", settings=settings)
            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["model"] == settings.reason_model

    def test_uses_default_model_when_reason_model_is_none(self):
        """When settings.reason_model is None, falls back to _DEFAULT_MODEL."""
        from app.config import Settings
        settings_no_model = Settings(
            openai_api_key="sk-test",
            anthropic_api_key="sk-ant-test",
            reason_model=None,
        )
        payload = {
            "label": "EXTENDS",
            "reason": "x",
            "matched_item_id": None,
            "confidence": 0.6,
        }
        with patch("anthropic.Anthropic") as MockAnthropic:
            mock_client = MockAnthropic.return_value
            mock_client.messages.create.return_value = (
                _make_anthropic_response(payload)
            )
            classify("system", "user", settings=settings_no_model)
            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["model"] is not None
            assert isinstance(call_kwargs["model"], str)

    def test_reason_preserved_in_collapse(self, settings):
        """When collapsing to NOT_RELEVANT, the original reason is kept."""
        payload = {
            "label": "ANSWERS",
            "reason": "Kind of relevant but not enough.",
            "matched_item_id": "oq_1",
            "confidence": 0.2,
        }
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = (
                _make_anthropic_response(payload)
            )
            result = classify("system", "user", settings=settings)
        assert result.label == Label.NOT_RELEVANT
        assert result.reason == "Kind of relevant but not enough."

    def test_all_labels_parseable(self, settings):
        """Every valid label string should parse without error."""
        for label_str in ["ANSWERS", "CONTRADICTS", "EXTENDS", "NOT_RELEVANT", "SCOOP"]:
            payload = {
                "label": label_str,
                "reason": "test",
                "matched_item_id": None,
                "confidence": 0.9,
            }
            with patch("anthropic.Anthropic") as MockAnthropic:
                MockAnthropic.return_value.messages.create.return_value = (
                    _make_anthropic_response(payload)
                )
                result = classify("system", "user", settings=settings)
            assert result.label.value == label_str
