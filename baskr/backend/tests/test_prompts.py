"""Phase 2 — prompts.build_prompt renders the SPEC §7 contract deterministically."""

from __future__ import annotations

from app.models import PaperOut, ProfileItem, ProfileItemKind
from app.prompts import SYSTEM_PROMPT, build_prompt


def _items() -> list[ProfileItem]:
    return [
        ProfileItem(id="oq_1", kind=ProfileItemKind.OPEN_QUESTION,
                    text="Does SCFA production modulate gut inflammation?"),
        ProfileItem(id="asm_1", kind=ProfileItemKind.ASSUMPTION,
                    text="Butyrate supports regulatory T cell differentiation."),
    ]


def _paper() -> PaperOut:
    return PaperOut(
        source="pubmed",
        source_id="39876543",
        title="Butyrate and intestinal Treg induction",
        abstract="We show butyrate promotes Treg differentiation in the colon.",
    )


def test_system_is_system_prompt() -> None:
    system, _ = build_prompt(_items(), _paper())
    assert system == SYSTEM_PROMPT


def test_user_contains_each_item_id_kind_text() -> None:
    _, user = build_prompt(_items(), _paper())
    for item in _items():
        assert item.id in user
        assert item.kind.value in user
        assert item.text in user
        # Rendered exactly as `- [{id} · {kind}] {text}` per SPEC §7.
        assert f"- [{item.id} · {item.kind.value}] {item.text}" in user


def test_user_contains_paper_title_and_abstract() -> None:
    paper = _paper()
    _, user = build_prompt(_items(), paper)
    assert f"Title: {paper.title}" in user
    assert f"Abstract: {paper.abstract}" in user


def test_user_contains_json_contract_keys() -> None:
    _, user = build_prompt(_items(), _paper())
    assert "Return strict JSON only:" in user
    for key in ("label", "reason", "matched_item_id", "confidence"):
        assert f'"{key}"' in user


def test_structure_snapshot() -> None:
    """Snapshot the overall structure / ordering of the user message."""
    _, user = build_prompt(_items(), _paper())
    assert user.index("LAB PROFILE:") < user.index("NEW PAPER:")
    assert user.index("NEW PAPER:") < user.index("Return strict JSON only:")
    assert user.startswith("LAB PROFILE:")


def test_deterministic() -> None:
    a = build_prompt(_items(), _paper())
    b = build_prompt(_items(), _paper())
    assert a == b
