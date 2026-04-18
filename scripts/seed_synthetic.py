"""零数据冷启动种子。

为节日类生成 10-20 个"合成理想范本"，打上 `is_synthetic=True` 标记，
写入 Postgres + Qdrant。Eval 时排除 synthetic 样本，但 Planner 检索会用到它们
让系统在真实数据到来前有"参照物"。

Usage:
    python scripts/seed_synthetic.py --category festival
    python scripts/seed_synthetic.py --category festival --n 20
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import click

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from card_pack_agent.logging import configure_logging  # noqa: E402
from card_pack_agent.memory.postgres import case_store  # noqa: E402
from card_pack_agent.memory.vector import COLLECTION_TOPIC, embed, vector_store  # noqa: E402
from card_pack_agent.schemas import (  # noqa: E402
    BGMSuggestion,
    CardPrompt,
    CaseRecord,
    Classification,
    CopyDirection,
    CTA,
    L1,
    L2,
    PackStructure,
    ScriptHint,
    Segment,
    SegmentRole,
    Script,
    Shot,
    StrategyDoc,
    TextOverlay,
    TextOverlayHint,
    Tier,
    VisualDirection,
)


# --- Festival synthetic templates ---

FESTIVAL_SEEDS = [
    # (topic, l2, tier, palette, main_subject, hook_overlay)
    ("中秋节 · 独在异乡的年轻人", L2.RESONANCE_HEALING, Tier.VIRAL,
     ["#F5A623", "#E8824A", "#FFF8E7"], "a bowl of tangyuan on a windowsill",
     "今年你一个人过中秋吗"),
    ("中秋节 · 家人的等待", L2.REGRET_STING, Tier.GOOD,
     ["#D4A574", "#8B6F47", "#F2E8D5"], "empty chair at dinner table",
     "妈妈多留了一副碗筷"),
    ("中秋节 · 送礼攻略", L2.UTILITY_SHARE, Tier.GOOD,
     ["#C8323F", "#F5A623", "#FFFFFF"], "moon cake gift box arranged flatlay",
     "15款中秋送礼清单"),

    ("春节 · 回家路上", L2.RESONANCE_HEALING, Tier.VIRAL,
     ["#C8323F", "#F5A623", "#2C2C2A"], "train window blurred night scenery",
     "你还记得第一次独自回家吗"),
    ("春节 · 爷爷奶奶的年", L2.REGRET_STING, Tier.VIRAL,
     ["#8B6F47", "#D4A574", "#F2E8D5"], "old wooden door with faded couplet",
     "这是爷爷贴的最后一副对联"),
    ("春节 · 祝福给想到的人", L2.BLESSING_RITUAL, Tier.GOOD,
     ["#C8323F", "#F5A623"], "paper lanterns against dusk sky",
     "愿你今年不再独自硬撑"),

    ("母亲节 · 子欲养而亲不待", L2.REGRET_STING, Tier.VIRAL,
     ["#8B6F47", "#D4A574"], "old reading glasses on open book",
     "她的老花镜还在桌上"),
    ("母亲节 · 妈妈的日常", L2.RESONANCE_HEALING, Tier.GOOD,
     ["#E8824A", "#FFF8E7"], "hands peeling fruit close-up warm light",
     "妈妈的手什么时候变成这样的"),
    ("母亲节 · 反差叙事", L2.CONTRAST_TWIST, Tier.GOOD,
     ["#F5A623", "#2C2C2A"], "phone screen with unsent message",
     "别人都在发祝福 而我"),

    ("情人节 · 一个人的浪漫", L2.CONFLICT_TENSION, Tier.GOOD,
     ["#D4537E", "#F2E8D5"], "single wine glass on balcony", "别人双双对对 你一个人也能"),
    ("清明 · 思念的方式", L2.REGRET_STING, Tier.GOOD,
     ["#B4B2A9", "#5F5E5A"], "old photograph in a frame", "他的笑还停在照片里"),
    ("圣诞节 · 都市孤独", L2.RESONANCE_HEALING, Tier.GOOD,
     ["#1D9E75", "#C8323F", "#FFFFFF"], "lone figure against lit shop window",
     "橱窗里的暖 隔着一层玻璃"),
    ("七夕 · 不是所有人都过节", L2.CONFLICT_TENSION, Tier.GOOD,
     ["#D4537E", "#2C2C2A"], "empty movie theater seat next to one occupied",
     "而我今晚加班到十点"),
    ("教师节 · 想念你的那位老师", L2.RESONANCE_HEALING, Tier.GOOD,
     ["#D4A574", "#F2E8D5"], "chalk on green blackboard close-up",
     "你还记得黑板最后一行字吗"),
    ("生日 · 长大后的生日", L2.CONTRAST_TWIST, Tier.GOOD,
     ["#F5A623", "#FFF8E7"], "single candle on convenience store cake",
     "小时候的生日vs现在"),
]


def _make_synthetic_pack(topic: str, l2: L2, tier: Tier, palette: list[str],
                         main_subject: str, hook_overlay: str,
                         created_at: datetime) -> CaseRecord:
    """Build a minimum-viable CaseRecord for seeding."""
    total = 50

    segments = [
        Segment(range=(1, 3), role=SegmentRole.HOOK, notes="single object, warm"),
        Segment(range=(4, 15), role=SegmentRole.SETUP, notes="scene fragments"),
        Segment(range=(16, 35), role=SegmentRole.DEVELOPMENT, notes="memory details"),
        Segment(range=(36, 45), role=SegmentRole.TURN, notes="soft turn"),
        Segment(range=(46, 50), role=SegmentRole.CLOSE, notes="quiet close"),
    ]

    strategy = StrategyDoc(
        version="1.0",
        topic=topic,
        classification=Classification(
            l1=L1.FESTIVAL, l2=l2,
            l3=["palette:warm", "text:minimal", "subject:single_object",
                "pace:slow", "cta:soft", "style:realistic"],
            reasoning=f"Synthetic seed for {l2.value}",
        ),
        referenced_cases=[],
        structure=PackStructure(total_cards=total, segments=segments),
        visual_direction=VisualDirection(
            palette=palette,
            main_subject=main_subject,
            composition_note="large negative space for text overlay",
            style_anchor="film photography, 35mm, natural light",
        ),
        copy_direction=CopyDirection(
            tone="克制、温柔、具体",
            text_density="minimal",
            pronoun="你",
            hook_type="单意象 + 短句",
            cta=CTA(intensity="soft", example="评论区说说你的"),
        ),
        avoid=["全家团圆刻板叙事", "连续情绪渲染词"],
        script_hint=ScriptHint(
            narrative_arc="意象 → 场景 → 回忆 → 当下 → 留白",
            pacing_note="约 35-40s 总时长",
        ),
    )

    cards = []
    for i in range(1, total + 1):
        if i <= 3:
            seg = SegmentRole.HOOK
            overlay = hook_overlay if i == 1 else f"{topic} 场景 {i}"
        elif i <= 15:
            seg = SegmentRole.SETUP
            overlay = f"{topic} 细节 {i}"
        elif i <= 35:
            seg = SegmentRole.DEVELOPMENT
            overlay = None if i % 5 == 0 else f"{topic} 展开 {i}"
        elif i <= 45:
            seg = SegmentRole.TURN
            overlay = f"{topic} 转折 {i}"
        else:
            seg = SegmentRole.CLOSE
            overlay = None if i % 2 == 0 else f"{topic} 收尾 {i}"

        cards.append(CardPrompt(
            position=i,
            segment=seg,
            prompt=(
                f"{main_subject}, {', '.join(palette)}, film photography, 35mm, "
                f"natural light, shallow depth of field, negative space for overlay"
            ),
            negative_prompt="text, watermark, logo, typography, captions",
            composition_note="subject lower-third, ample top negative space",
            text_overlay_hint=(
                TextOverlayHint(
                    content_suggestion=overlay,
                    position="top-center" if i <= 3 else "bottom-center",
                    size_tier="hook" if i <= 3 else "body",
                ) if overlay else None
            ),
        ))

    script = Script(
        version="1.0",
        total_duration_s=38.0,
        bgm_suggestion=BGMSuggestion(
            mood="slow, warm, acoustic piano",
            reference="(synthetic reference)",
            tempo_curve="slow throughout with subtle swell around card 30",
        ),
        has_voiceover=False,
        shots=[
            Shot(
                position=c.position,
                duration_s=2.0 if c.position <= 3 or c.position >= 46 else 0.8,
                text_overlay=(
                    TextOverlay(
                        content=c.text_overlay_hint.content_suggestion,
                        position=c.text_overlay_hint.position,
                        size_tier=c.text_overlay_hint.size_tier,
                    ) if c.text_overlay_hint else None
                ),
            )
            for c in cards
        ],
        key_moments=[],
    )

    return CaseRecord(
        pack_id=uuid4(),
        topic=topic,
        topic_l1=L1.FESTIVAL,
        topic_l2=l2,
        topic_l3=strategy.classification.l3,
        strategy_doc=strategy,
        cards=cards,
        script=script,
        metrics=None,
        tier=tier,
        is_exploration=False,
        is_synthetic=True,
        created_at=created_at,
    )


@click.command()
@click.option("--category", default="festival", help="L1 category")
@click.option("--n", default=None, type=int, help="Number of seeds (default: all)")
def main(category: str, n: int | None) -> None:
    configure_logging()
    if category != "festival":
        click.echo(f"only 'festival' has seed templates for now; got {category}")
        sys.exit(1)

    seeds = FESTIVAL_SEEDS[:n] if n else FESTIVAL_SEEDS
    base_date = datetime.utcnow() - timedelta(days=60)

    click.echo(f"seeding {len(seeds)} synthetic packs for {category}...")
    for i, (topic, l2, tier, palette, main_subject, hook_overlay) in enumerate(seeds):
        # Stagger dates so time-decay retrieval has something to work with
        created_at = base_date + timedelta(days=i * 3)
        case = _make_synthetic_pack(topic, l2, tier, palette, main_subject,
                                    hook_overlay, created_at)
        case_store.insert(case)

        # Index in vector store
        vector = embed(case.topic)
        vector_store.upsert(
            collection=COLLECTION_TOPIC,
            point_id=str(case.pack_id),
            vector=vector,
            payload={
                "pack_id": str(case.pack_id),
                "topic": case.topic,
                "l1": case.topic_l1.value,
                "l2": case.topic_l2.value,
                "tier": case.tier.value if case.tier else "bad",
                "is_synthetic": True,
                "created_at": created_at.isoformat(),
            },
        )
        click.echo(f"  [{i+1}/{len(seeds)}] {topic} ({l2.value}, {tier.value})")

    click.echo("done.")


if __name__ == "__main__":
    main()
