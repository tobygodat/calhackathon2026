"""Unit tests for the OpenAI embeddings wrapper (app/embeddings.py).

Note: embed_text/embed_batch import OpenAI lazily inside the function body,
so we must patch ``openai.OpenAI`` (the source), not ``app.embeddings.OpenAI``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.embeddings import embed_batch, embed_text


def _mock_embedding() -> list[float]:
    """Return a fake 1536-dim embedding."""
    return [0.1] * 1536


def _make_openai_response(embeddings: list[list[float]]) -> MagicMock:
    """Build a mock OpenAI embeddings response."""
    mock_resp = MagicMock()
    items = []
    for idx, emb in enumerate(embeddings):
        item = MagicMock()
        item.embedding = emb
        item.index = idx
        items.append(item)
    mock_resp.data = items
    return mock_resp


class TestEmbedText:
    def test_returns_list_of_floats(self, settings):
        fake_emb = _mock_embedding()
        with patch("openai.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.embeddings.create.return_value = (
                _make_openai_response([fake_emb])
            )
            result = embed_text("test text", settings=settings)
        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)

    def test_returns_1536_dimensions(self, settings):
        fake_emb = _mock_embedding()
        with patch("openai.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.embeddings.create.return_value = (
                _make_openai_response([fake_emb])
            )
            result = embed_text("test text", settings=settings)
        assert len(result) == 1536

    def test_calls_openai_with_correct_model(self, settings):
        with patch("openai.OpenAI") as MockOpenAI:
            mock_client = MockOpenAI.return_value
            mock_client.embeddings.create.return_value = (
                _make_openai_response([_mock_embedding()])
            )
            embed_text("hello", settings=settings)
            mock_client.embeddings.create.assert_called_once()
            call_kwargs = mock_client.embeddings.create.call_args.kwargs
            assert call_kwargs["model"] == settings.embed_model
            assert call_kwargs["input"] == "hello"

    def test_uses_api_key_from_settings(self, settings):
        with patch("openai.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.embeddings.create.return_value = (
                _make_openai_response([_mock_embedding()])
            )
            embed_text("x", settings=settings)
            MockOpenAI.assert_called_once_with(api_key=settings.openai_api_key)

    def test_empty_string_input(self, settings):
        fake_emb = _mock_embedding()
        with patch("openai.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.embeddings.create.return_value = (
                _make_openai_response([fake_emb])
            )
            result = embed_text("", settings=settings)
        assert len(result) == 1536


class TestEmbedBatch:
    def test_returns_list_of_embeddings(self, settings):
        texts = ["text one", "text two", "text three"]
        fake_embs = [_mock_embedding() for _ in texts]
        with patch("openai.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.embeddings.create.return_value = (
                _make_openai_response(fake_embs)
            )
            result = embed_batch(texts, settings=settings)
        assert len(result) == 3
        assert all(len(e) == 1536 for e in result)

    def test_empty_list_returns_empty(self, settings):
        result = embed_batch([], settings=settings)
        assert result == []

    def test_single_text(self, settings):
        fake_emb = _mock_embedding()
        with patch("openai.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.embeddings.create.return_value = (
                _make_openai_response([fake_emb])
            )
            result = embed_batch(["single"], settings=settings)
        assert len(result) == 1

    def test_preserves_order(self, settings):
        """Embeddings are sorted by index field so order is preserved."""
        emb_a = [0.1] * 1536
        emb_b = [0.9] * 1536
        mock_resp = MagicMock()
        # Intentionally return b before a (reversed) to test sort-by-index
        item_b = MagicMock()
        item_b.embedding = emb_b
        item_b.index = 1
        item_a = MagicMock()
        item_a.embedding = emb_a
        item_a.index = 0
        mock_resp.data = [item_b, item_a]  # reversed

        with patch("openai.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.embeddings.create.return_value = mock_resp
            result = embed_batch(["a", "b"], settings=settings)
        assert result[0] == emb_a
        assert result[1] == emb_b
