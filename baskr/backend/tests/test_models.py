"""Unit tests for Pydantic data models (app/models.py)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import (
    Classification,
    DigestEntry,
    DigestSummary,
    Label,
    MemoryWriteRequest,
    PaperOut,
    Profile,
    ProfileItem,
    ProfileItemKind,
    SearchHit,
    SearchRequest,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestLabel:
    def test_all_values(self):
        assert set(Label) == {
            Label.ANSWERS,
            Label.CONTRADICTS,
            Label.EXTENDS,
            Label.NOT_RELEVANT,
            Label.SCOOP,
        }

    def test_string_values(self):
        assert Label.ANSWERS.value == "ANSWERS"
        assert Label.NOT_RELEVANT.value == "NOT_RELEVANT"

    def test_from_string(self):
        assert Label("ANSWERS") == Label.ANSWERS
        assert Label("NOT_RELEVANT") == Label.NOT_RELEVANT

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            Label("INVALID_LABEL")


class TestProfileItemKind:
    def test_values(self):
        assert ProfileItemKind.OPEN_QUESTION.value == "open_question"
        assert ProfileItemKind.PLANNED_EXPERIMENT.value == "planned_experiment"


# ---------------------------------------------------------------------------
# ProfileItem / Profile
# ---------------------------------------------------------------------------

class TestProfileItem:
    def test_create(self):
        item = ProfileItem(id="oq_1", kind=ProfileItemKind.OPEN_QUESTION, text="How?")
        assert item.id == "oq_1"
        assert item.kind == ProfileItemKind.OPEN_QUESTION
        assert item.text == "How?"

    def test_kind_coercion_from_string(self):
        item = ProfileItem(id="x", kind="finding", text="We found X.")
        assert item.kind == ProfileItemKind.FINDING

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            ProfileItem(id="x", kind=ProfileItemKind.FINDING)  # missing text


class TestProfile:
    def test_default_items(self):
        p = Profile(lab_id="lab", niche="gut", display_name="Lab")
        assert p.items == []

    def test_with_items(self, sample_profile):
        assert len(sample_profile.items) == 3
        assert sample_profile.lab_id == "test-lab"

    def test_serialization_roundtrip(self, sample_profile):
        json_str = sample_profile.model_dump_json()
        restored = Profile.model_validate_json(json_str)
        assert restored == sample_profile


# ---------------------------------------------------------------------------
# PaperOut
# ---------------------------------------------------------------------------

class TestPaperOut:
    def test_minimal(self):
        paper = PaperOut(source="pubmed", source_id="1", title="Test")
        assert paper.abstract == ""
        assert paper.authors == []
        assert paper.doi is None
        assert paper.uid is None

    def test_full_fields(self, sample_paper):
        assert sample_paper.source == "pubmed"
        assert sample_paper.published == "2024-03-15"
        assert "Smith" in sample_paper.authors[0]

    def test_serialization(self, sample_paper):
        d = sample_paper.model_dump()
        assert d["source"] == "pubmed"
        assert d["title"] == "Gut Microbiome Modulation by Dietary Fiber"


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

class TestClassification:
    def test_create(self):
        c = Classification(
            label=Label.EXTENDS,
            reason="Extends prior work.",
            confidence=0.75,
        )
        assert c.matched_item_id is None
        assert c.confidence == 0.75

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            Classification(label=Label.ANSWERS, reason="x", confidence=1.5)
        with pytest.raises(ValidationError):
            Classification(label=Label.ANSWERS, reason="x", confidence=-0.1)

    def test_label_coercion(self):
        c = Classification(label="CONTRADICTS", reason="x", confidence=0.8)
        assert c.label == Label.CONTRADICTS


# ---------------------------------------------------------------------------
# DigestEntry / DigestSummary
# ---------------------------------------------------------------------------

class TestDigestEntry:
    def test_create(self, sample_paper, answers_classification):
        entry = DigestEntry(
            date="2024-03-15",
            paper=sample_paper,
            classification=answers_classification,
        )
        assert entry.date == "2024-03-15"
        assert entry.paper.title == sample_paper.title
        assert entry.classification.label == Label.ANSWERS

    def test_serialization(self, sample_paper, answers_classification):
        entry = DigestEntry(
            date="2024-03-15",
            paper=sample_paper,
            classification=answers_classification,
        )
        d = entry.model_dump()
        assert d["date"] == "2024-03-15"
        assert d["classification"]["label"] == "ANSWERS"


class TestDigestSummary:
    def test_create(self):
        s = DigestSummary(date="2024-03-15", count=5, top_label=Label.EXTENDS)
        assert s.date == "2024-03-15"
        assert s.count == 5
        assert s.top_label == Label.EXTENDS


# ---------------------------------------------------------------------------
# Request / Response bodies
# ---------------------------------------------------------------------------

class TestSearchRequest:
    def test_create(self):
        r = SearchRequest(question="How does fiber affect microbiome?")
        assert r.question == "How does fiber affect microbiome?"

    def test_missing_question(self):
        with pytest.raises(ValidationError):
            SearchRequest()


class TestSearchHit:
    def test_create(self, sample_paper, answers_classification):
        hit = SearchHit(paper=sample_paper, classification=answers_classification)
        assert hit.paper.source == "pubmed"
        assert hit.classification.confidence == 0.92


class TestMemoryWriteRequest:
    def test_create(self):
        req = MemoryWriteRequest(kind=ProfileItemKind.FINDING, text="New finding.")
        assert req.kind == ProfileItemKind.FINDING
        assert req.text == "New finding."

    def test_kind_from_string(self):
        req = MemoryWriteRequest(kind="assumption", text="We assume X.")
        assert req.kind == ProfileItemKind.ASSUMPTION
