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


# --- opt-in PRIOR WORK section ---------------------------------------------

def _prior() -> list[dict]:
    return [
        {"title": "SCFA and colonic Tregs", "abstract": "Earlier work on butyrate.",
         "uid": "p1"},
        {"title": "Fiber fermentation review", "abstract": "Survey of SCFA output.",
         "uid": "p2"},
    ]


def test_no_prior_work_is_byte_identical_to_default() -> None:
    """Passing None/[] for prior_work yields exactly the old output (default path
    unchanged)."""
    base = build_prompt(_items(), _paper())
    assert build_prompt(_items(), _paper(), prior_work=None) == base
    assert build_prompt(_items(), _paper(), prior_work=[]) == base


def test_prior_work_section_rendered_between_profile_and_paper() -> None:
    _, user = build_prompt(_items(), _paper(), prior_work=_prior())
    assert "PRIOR WORK:" in user
    assert user.index("LAB PROFILE:") < user.index("PRIOR WORK:")
    assert user.index("PRIOR WORK:") < user.index("NEW PAPER:")
    for rec in _prior():
        assert rec["title"] in user


def test_degraded_parser_skips_prior_work() -> None:
    """llm._parse_user_prompt must recover the SAME profile items and paper text
    whether or not a PRIOR WORK section is present (keeps the no-API-key path
    working)."""
    from app.llm import _parse_user_prompt

    _, plain = build_prompt(_items(), _paper())
    _, withprior = build_prompt(_items(), _paper(), prior_work=_prior())
    assert _parse_user_prompt(plain) == _parse_user_prompt(withprior)
    items, paper_text = _parse_user_prompt(withprior)
    assert [i[0] for i in items] == ["oq_1", "asm_1"]
    # Prior-work titles must not leak into the recovered paper text.
    assert "SCFA and colonic Tregs" not in paper_text
