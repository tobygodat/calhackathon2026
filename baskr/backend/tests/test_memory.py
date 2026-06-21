"""Unit tests for the memory / profile module (app/memory.py).

memory.py imports lazily from seed_profile and caches the profile at module level.
Tests reset _profile_cache and, where needed, patch app.memory.load_seed.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import app.memory as mem
from app.memory import append_item, load_profile, retrieve_relevant
from app.models import Profile, ProfileItem, ProfileItemKind


@pytest.fixture(autouse=True)
def reset_profile_cache():
    """Each test starts with a fresh profile cache."""
    mem._profile_cache = None
    yield
    mem._profile_cache = None


def _make_profile(items: list[ProfileItem] | None = None) -> Profile:
    return Profile(
        lab_id="test-lab",
        niche="gut_microbiome",
        display_name="Test Lab",
        items=items or [
            ProfileItem(id="oq_1", kind=ProfileItemKind.OPEN_QUESTION,
                        text="How does fiber affect Akkermansia?"),
            ProfileItem(id="asm_1", kind=ProfileItemKind.ASSUMPTION,
                        text="Fiber promotes SCFA production."),
            ProfileItem(id="fnd_1", kind=ProfileItemKind.FINDING,
                        text="Inulin increases Bifidobacterium."),
        ],
    )


class TestLoadProfile:
    def test_returns_profile_object(self):
        profile = load_profile()
        assert isinstance(profile, Profile)

    def test_has_lab_id(self):
        profile = load_profile()
        assert profile.lab_id  # non-empty

    def test_has_display_name(self):
        profile = load_profile()
        assert profile.display_name  # non-empty

    def test_items_are_profile_items(self):
        profile = load_profile()
        for item in profile.items:
            assert isinstance(item, ProfileItem)

    def test_item_kinds_are_valid(self):
        profile = load_profile()
        valid_kinds = set(ProfileItemKind)
        for item in profile.items:
            assert item.kind in valid_kinds

    def test_items_have_non_empty_text(self):
        profile = load_profile()
        for item in profile.items:
            assert item.text.strip()

    def test_seed_has_at_least_three_items(self):
        """The default seed JSON has 3 placeholder items."""
        profile = load_profile()
        assert len(profile.items) >= 3

    def test_caching_returns_same_object(self):
        """Second call returns the cached profile (same object identity)."""
        p1 = load_profile()
        p2 = load_profile()
        assert p1 is p2

    def test_load_seed_called_only_once(self):
        """load_seed is only called on first invocation."""
        with patch("app.memory.load_seed", return_value=_make_profile()) as mock_seed:
            load_profile()
            load_profile()
        mock_seed.assert_called_once()


class TestRetrieveRelevant:
    def test_returns_list_of_profile_items(self):
        with patch("app.memory.load_seed", return_value=_make_profile()):
            result = retrieve_relevant("fiber and gut microbiome")
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, ProfileItem)

    def test_respects_k_limit(self):
        profile = _make_profile()
        k = max(1, len(profile.items) - 1)
        with patch("app.memory.load_seed", return_value=profile):
            result = retrieve_relevant("some query", k=k)
        assert len(result) <= k

    def test_returns_all_when_k_exceeds_count(self):
        profile = _make_profile()
        with patch("app.memory.load_seed", return_value=profile):
            result = retrieve_relevant("query", k=100)
        assert len(result) == len(profile.items)

    def test_k_zero_returns_empty(self):
        with patch("app.memory.load_seed", return_value=_make_profile()):
            result = retrieve_relevant("query", k=0)
        assert result == []

    def test_empty_profile_returns_empty(self):
        empty_profile = Profile(lab_id="l", niche="n", display_name="d", items=[])
        with patch("app.memory.load_seed", return_value=empty_profile):
            result = retrieve_relevant("query")
        assert result == []


class TestAppendItem:
    def _seed_profile_one_item(self) -> Profile:
        return Profile(
            lab_id="test-lab",
            niche="gut",
            display_name="Test Lab",
            items=[
                ProfileItem(id="oq_1", kind=ProfileItemKind.OPEN_QUESTION,
                            text="Initial question."),
            ],
        )

    def test_appends_new_item(self, tmp_path):
        """append_item increases profile item count by 1 and persists to JSON."""
        seed_file = tmp_path / "profile_seed.json"
        seed_file.write_text("{}", encoding="utf-8")  # placeholder, won't be read

        with patch("app.memory.load_seed", return_value=self._seed_profile_one_item()):
            with patch("app.memory.SEED_PATH", seed_file):
                updated = append_item(ProfileItemKind.FINDING,
                                      "New finding about butyrate.")

        assert len(updated.items) == 2
        last = updated.items[-1]
        assert last.kind == ProfileItemKind.FINDING
        assert last.text == "New finding about butyrate."
        assert last.id.startswith("fin_")  # "finding"[:3] == "fin"

    def test_returns_updated_profile(self, tmp_path):
        seed_file = tmp_path / "profile_seed.json"
        seed_file.write_text("{}", encoding="utf-8")

        empty = Profile(lab_id="test-lab", niche="gut",
                        display_name="Test Lab", items=[])
        with patch("app.memory.load_seed", return_value=empty):
            with patch("app.memory.SEED_PATH", seed_file):
                result = append_item(ProfileItemKind.ASSUMPTION, "We assume X.")

        assert isinstance(result, Profile)
        assert any(it.text == "We assume X." for it in result.items)

    def test_new_item_id_includes_kind_prefix(self, tmp_path):
        """Item id starts with first 3 chars of the kind value."""
        seed_file = tmp_path / "profile_seed.json"
        seed_file.write_text("{}", encoding="utf-8")

        empty = Profile(lab_id="test-lab", niche="gut",
                        display_name="Test Lab", items=[])
        with patch("app.memory.load_seed", return_value=empty):
            with patch("app.memory.SEED_PATH", seed_file):
                result = append_item(ProfileItemKind.OPEN_QUESTION, "New question?")

        new_item = result.items[-1]
        # kind.value = "open_question" → kind.value[:3] = "ope"
        assert new_item.id.startswith("ope")

    def test_persisted_to_json(self, tmp_path):
        """After append_item, the JSON file on disk has the new item."""
        seed_file = tmp_path / "profile_seed.json"
        seed_file.write_text("{}", encoding="utf-8")

        empty = Profile(lab_id="test-lab", niche="gut",
                        display_name="Test Lab", items=[])
        with patch("app.memory.load_seed", return_value=empty):
            with patch("app.memory.SEED_PATH", seed_file):
                append_item(ProfileItemKind.FINDING, "Persisted finding.")

        saved = json.loads(seed_file.read_text(encoding="utf-8"))
        texts = [it["text"] for it in saved["items"]]
        assert "Persisted finding." in texts
