"""Unit tests for prompt construction (app/prompts.py)."""

from __future__ import annotations

import pytest

from app.models import PaperOut, ProfileItem, ProfileItemKind
from app.prompts import SYSTEM_PROMPT, build_prompt


def make_item(id: str, kind: ProfileItemKind, text: str) -> ProfileItem:
    return ProfileItem(id=id, kind=kind, text=text)


def make_paper(title: str = "Test Paper", abstract: str = "Some abstract.") -> PaperOut:
    return PaperOut(source="pubmed", source_id="1", title=title, abstract=abstract)


class TestBuildPrompt:
    def test_returns_tuple_of_two_strings(self, sample_paper, sample_profile):
        result = build_prompt(sample_profile.items, sample_paper)
        assert isinstance(result, tuple)
        assert len(result) == 2
        system, user = result
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_system_is_constant(self, sample_paper, sample_profile):
        system, _ = build_prompt(sample_profile.items, sample_paper)
        assert system == SYSTEM_PROMPT

    def test_system_mentions_baskr(self):
        assert "Baskr" in SYSTEM_PROMPT

    def test_user_contains_paper_title(self, sample_paper, sample_profile):
        _, user = build_prompt(sample_profile.items, sample_paper)
        assert sample_paper.title in user

    def test_user_contains_paper_abstract(self, sample_paper, sample_profile):
        _, user = build_prompt(sample_profile.items, sample_paper)
        assert "Akkermansia" in user  # part of the sample paper abstract

    def test_user_contains_profile_item_text(self, sample_paper, sample_profile):
        _, user = build_prompt(sample_profile.items, sample_paper)
        for item in sample_profile.items:
            assert item.text in user

    def test_user_contains_item_ids(self, sample_paper, sample_profile):
        _, user = build_prompt(sample_profile.items, sample_paper)
        for item in sample_profile.items:
            assert item.id in user

    def test_user_requests_json_output(self, sample_paper, sample_profile):
        _, user = build_prompt(sample_profile.items, sample_paper)
        assert "JSON" in user
        assert "label" in user
        assert "confidence" in user

    def test_empty_items_list(self, sample_paper):
        _, user = build_prompt([], sample_paper)
        assert "no profile items" in user.lower()

    def test_no_abstract_fallback(self):
        paper = make_paper(title="No Abstract Paper", abstract="")
        items = [make_item("oq_1", ProfileItemKind.OPEN_QUESTION, "Some question?")]
        _, user = build_prompt(items, paper)
        assert "No Abstract Paper" in user
        assert "no abstract" in user.lower()

    def test_item_kind_in_prompt(self, sample_paper, sample_profile):
        _, user = build_prompt(sample_profile.items, sample_paper)
        # Kind labels are formatted as uppercase
        assert "OPEN_QUESTION" in user or "open_question" in user.lower()

    def test_multiple_items_all_appear(self):
        items = [
            make_item("oq_1", ProfileItemKind.OPEN_QUESTION, "Question about fiber?"),
            make_item("asm_1", ProfileItemKind.ASSUMPTION, "Fiber helps microbiome."),
            make_item("fnd_1", ProfileItemKind.FINDING, "Akkermansia increased."),
        ]
        paper = make_paper()
        _, user = build_prompt(items, paper)
        assert "Question about fiber?" in user
        assert "Fiber helps microbiome." in user
        assert "Akkermansia increased." in user

    def test_json_schema_has_all_fields(self, sample_paper, sample_profile):
        _, user = build_prompt(sample_profile.items, sample_paper)
        for field in ["label", "reason", "matched_item_id", "confidence"]:
            assert field in user
