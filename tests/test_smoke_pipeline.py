"""End-to-end pipeline smoke test. Runs the full orchestrator in mock mode.

Exercises: Planner → Generator (cards + script) → Evaluator → persist
All LLM calls return canned data (see llm.py _canned_response).
"""
from __future__ import annotations

import pytest


@pytest.mark.smoke
def test_end_to_end_mock_pipeline():
    from card_pack_agent.orchestrator import run
    from card_pack_agent.schemas import TopicInput

    result = run(
        TopicInput(raw_topic="中秋节 独在异乡的年轻人"),
        hint_l1="festival",
        hint_l2="resonance_healing",
        generate_images=False,
        persist=True,
    )

    # Should not require clarification in mock mode
    assert result.clarification is None

    # Pack should exist and be well-formed
    assert result.pack is not None
    pack = result.pack
    assert len(pack.cards) == 50
    # Script is a teaser subset (6-10 cards) referencing real card positions
    assert 6 <= len(pack.script.shots) <= 10
    card_positions = {c.position for c in pack.cards}
    assert all(s.position in card_positions for s in pack.script.shots)
    assert pack.script.total_duration_s <= 15.5
    assert all(c.position == i for i, c in enumerate(pack.cards, start=1))

    # Evaluator should have run and populated scores
    assert result.evaluator_report is not None
    report = result.evaluator_report
    assert report.judge_scores, "judge should have produced scores in mock mode"
    # Mock judge returns 3.8 — safely above WARN threshold
    assert report.verdict.value in ("pass", "warn")


@pytest.mark.smoke
def test_seed_and_retrieve_roundtrip():
    """Seed a few synthetic packs, then confirm retrieval finds them."""
    from card_pack_agent.memory.vector import COLLECTION_TOPIC, embed, vector_store
    from card_pack_agent.tools.retrieve import retrieve_similar_packs
    from card_pack_agent.schemas import L1, L2, Tier

    # Seed one
    vector_store.upsert(
        collection=COLLECTION_TOPIC,
        point_id="test-seed-1",
        vector=embed("中秋节 独自在外"),
        payload={
            "pack_id": "test-seed-1",
            "topic": "中秋节 独自在外",
            "l1": "festival",
            "l2": "resonance_healing",
            "tier": "good",
            "is_synthetic": True,
            "created_at": "2026-03-01T00:00:00",
        },
    )

    hits = retrieve_similar_packs(
        topic="中秋节 一个人过",
        l1=L1.FESTIVAL,
        l2=L2.RESONANCE_HEALING,
        tier_gte=Tier.GOOD,
        top_k=3,
    )

    assert len(hits) >= 1
    assert hits[0].payload.get("l1") == "festival"
    assert hits[0].payload.get("l2") == "resonance_healing"


@pytest.mark.smoke
def test_evaluator_catches_banned_words():
    """Evaluator must fail a pack containing a banned word."""
    from card_pack_agent.schemas import (
        BGMSuggestion, CardPrompt, Classification, CopyDirection, CTA,
        L1, L2, Pack, PackStructure, Script, ScriptHint, Segment, SegmentRole,
        Shot, StrategyDoc, TextOverlay, TextOverlayHint, VisualDirection,
    )
    from card_pack_agent.tools.evaluator import check_banned_words
    from uuid import uuid4

    # Build a minimal pack with a banned word injected
    card = CardPrompt(
        position=1,
        segment=SegmentRole.HOOK,
        prompt="warm tones, single object",
        negative_prompt="text, watermark",
        text_overlay_hint=TextOverlayHint(
            content_suggestion="想自杀的夜晚",  # banned
            position="top-center",
            size_tier="hook",
        ),
    )
    pack = Pack(
        pack_id=uuid4(),
        topic="test",
        strategy=StrategyDoc(
            topic="test",
            classification=Classification(l1=L1.FESTIVAL, l2=L2.RESONANCE_HEALING, l3=[]),
            structure=PackStructure(total_cards=1, segments=[
                Segment(range=(1, 1), role=SegmentRole.HOOK),
            ]),
            visual_direction=VisualDirection(
                palette=["#F5A623"], main_subject="x", style_anchor="film",
            ),
            copy_direction=CopyDirection(
                tone="", text_density="minimal", hook_type="",
                cta=CTA(intensity="none"),
            ),
            script_hint=ScriptHint(narrative_arc="", pacing_note=""),
        ),
        cards=[card],
        script=Script(
            total_duration_s=2.0,
            bgm_suggestion=BGMSuggestion(mood=""),
            shots=[Shot(position=1, duration_s=2.0)],
        ),
    )

    issues = check_banned_words(pack)
    assert any(i.code == "banned_word_detected" for i in issues)


@pytest.mark.smoke
def test_reviewer_writes_experience_log(tmp_path, monkeypatch):
    """Reviewer should only write into experience_log/, never into categories/."""
    from card_pack_agent.memory.knowledge_loader import KnowledgeLoader

    # Point loader at a temp knowledge dir
    (tmp_path / "experience_log").mkdir()
    loader = KnowledgeLoader(base=tmp_path)

    written = loader.write_experience_log("2026-W15.md", "# test content")
    assert written.exists()
    assert written.parent.name == "experience_log"

    # Guardrail: rejects path traversal
    import pytest
    with pytest.raises(ValueError):
        loader.write_experience_log("../categories/festival.md", "bad")
