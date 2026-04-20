"""Zero-data cold-start seeder.

Builds 20-30 "ideal synthetic samples" per the current focus categories and
writes them to Postgres + Qdrant. Samples carry `is_synthetic=True` so offline
eval excludes them, but the Planner's retrieval can still find them.

The seed pool is bilingual on purpose (English is primary; a small Chinese
subset is retained as reference). All new packs should be generated in English
going forward; the CN entries serve as contrast examples during the English
ramp-up window.

Usage:
    python scripts/seed_synthetic.py                          # seed all English
    python scripts/seed_synthetic.py --category festival
    python scripts/seed_synthetic.py --category all --include-legacy-cn
    python scripts/seed_synthetic.py --n 10
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
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


@dataclass
class SeedSpec:
    """A minimal recipe for a synthetic pack."""

    topic: str
    l1: L1
    l2: L2
    tier: Tier
    palette: list[str]
    main_subject: str
    hook_overlay: str
    language: str = "en"  # "en" | "zh"
    l3: list[str] = field(default_factory=lambda: [
        "palette:warm", "text:minimal", "subject:single_object",
        "pace:slow", "cta:soft", "style:realistic",
    ])


# --- English festival seeds (primary) ---

EN_FESTIVAL_SEEDS: list[SeedSpec] = [
    # Thanksgiving
    SeedSpec(
        topic="Thanksgiving alone in the city",
        l1=L1.FESTIVAL, l2=L2.RESONANCE_HEALING, tier=Tier.VIRAL,
        palette=["#F5A623", "#E8824A", "#FFF8E7"],
        main_subject="a single set dinner plate on a small kitchen table",
        hook_overlay="eating alone this Thanksgiving",
    ),
    SeedSpec(
        topic="Thanksgiving · the one who isn't at the table",
        l1=L1.FESTIVAL, l2=L2.REGRET_STING, tier=Tier.GOOD,
        palette=["#D4A574", "#8B6F47", "#F2E8D5"],
        main_subject="an empty chair at a warmly lit dining table",
        hook_overlay="mom still set her place",
    ),
    # Christmas
    SeedSpec(
        topic="Christmas · last-minute gift guide under $30",
        l1=L1.FESTIVAL, l2=L2.UTILITY_SHARE, tier=Tier.GOOD,
        palette=["#C8323F", "#1D9E75", "#FFFFFF"],
        main_subject="curated small gifts in flatlay composition",
        hook_overlay="15 gifts under $30 they'll actually love",
        l3=["palette:high_contrast", "text:heavy", "subject:single_object",
            "pace:fast", "cta:hard", "style:typographic"],
    ),
    SeedSpec(
        topic="Christmas · first one without her",
        l1=L1.FESTIVAL, l2=L2.REGRET_STING, tier=Tier.VIRAL,
        palette=["#8B6F47", "#D4A574", "#F2E8D5"],
        main_subject="an old reading light next to a closed book",
        hook_overlay="her ornament is still in the box",
    ),
    SeedSpec(
        topic="Christmas Eve train ride home",
        l1=L1.FESTIVAL, l2=L2.RESONANCE_HEALING, tier=Tier.VIRAL,
        palette=["#2C2C2A", "#F5A623", "#FFF8E7"],
        main_subject="blurred window at night with soft station lights",
        hook_overlay="you remember your first trip home",
    ),
    # New Year's
    SeedSpec(
        topic="New Year's Eve · wishes for someone quiet",
        l1=L1.FESTIVAL, l2=L2.BLESSING_RITUAL, tier=Tier.GOOD,
        palette=["#C8323F", "#F5A623"],
        main_subject="paper lanterns against a dusk sky",
        hook_overlay="may this be your year to stop apologizing",
    ),
    # Valentine's Day
    SeedSpec(
        topic="Valentine's Day · solo and fine about it",
        l1=L1.FESTIVAL, l2=L2.CONFLICT_TENSION, tier=Tier.GOOD,
        palette=["#D4537E", "#F2E8D5"],
        main_subject="a single wine glass on a quiet balcony",
        hook_overlay="everyone is out. you're in. both are fine.",
    ),
    # Mother's Day
    SeedSpec(
        topic="Mother's Day · the things I never got to say",
        l1=L1.FESTIVAL, l2=L2.REGRET_STING, tier=Tier.VIRAL,
        palette=["#8B6F47", "#D4A574"],
        main_subject="old reading glasses resting on an open letter",
        hook_overlay="her glasses are still on the table",
    ),
    SeedSpec(
        topic="Mother's Day · the small things she did",
        l1=L1.FESTIVAL, l2=L2.RESONANCE_HEALING, tier=Tier.GOOD,
        palette=["#E8824A", "#FFF8E7"],
        main_subject="close-up of hands peeling fruit in warm light",
        hook_overlay="when did her hands get like that",
    ),
    SeedSpec(
        topic="Mother's Day · contrast post",
        l1=L1.FESTIVAL, l2=L2.CONTRAST_TWIST, tier=Tier.GOOD,
        palette=["#F5A623", "#2C2C2A"],
        main_subject="phone screen with a message typed but not sent",
        hook_overlay="everyone's posting her. I'm just sitting here.",
    ),
    # Father's Day
    SeedSpec(
        topic="Father's Day · the quiet ones",
        l1=L1.FESTIVAL, l2=L2.RESONANCE_HEALING, tier=Tier.GOOD,
        palette=["#4A5568", "#D4A574"],
        main_subject="a worn work jacket on the back of a chair",
        hook_overlay="he'd never say it out loud",
    ),
    # Halloween
    SeedSpec(
        topic="Halloween · costumes that aged weirdly",
        l1=L1.FESTIVAL, l2=L2.CONTRAST_TWIST, tier=Tier.GOOD,
        palette=["#FF8C00", "#2C2C2A"],
        main_subject="a single carved pumpkin on a porch at dusk",
        hook_overlay="what you wore then says a lot now",
        l3=["palette:high_contrast", "text:medium", "subject:single_object",
            "pace:medium", "cta:soft", "style:realistic"],
    ),
    # Birthday
    SeedSpec(
        topic="Birthday · grown-up birthdays",
        l1=L1.FESTIVAL, l2=L2.CONTRAST_TWIST, tier=Tier.GOOD,
        palette=["#F5A623", "#FFF8E7"],
        main_subject="a single candle on a grocery-store slice of cake",
        hook_overlay="8-year-old you vs now",
    ),
    # Lunar New Year (English narrative)
    SeedSpec(
        topic="Lunar New Year · first one abroad",
        l1=L1.FESTIVAL, l2=L2.RESONANCE_HEALING, tier=Tier.GOOD,
        palette=["#C8323F", "#F5A623", "#FFFFFF"],
        main_subject="a bowl of dumplings on a small kitchen counter",
        hook_overlay="your first new year this far from home",
    ),
    # Easter
    SeedSpec(
        topic="Easter · the Sunday after everything changed",
        l1=L1.FESTIVAL, l2=L2.REGRET_STING, tier=Tier.GOOD,
        palette=["#B4B2A9", "#5F5E5A"],
        main_subject="a pressed flower in an old hymnal",
        hook_overlay="his smile is still in the photo",
    ),
]


# --- English emotional seeds ---

EN_EMOTIONAL_SEEDS: list[SeedSpec] = [
    SeedSpec(
        topic="Burnout at 28",
        l1=L1.EMOTIONAL, l2=L2.RESONANCE_HEALING, tier=Tier.VIRAL,
        palette=["#3B5368", "#9CA7B4", "#F2E8D5"],
        main_subject="a desk lamp lit at 11pm, laptop half-closed",
        hook_overlay="you told them you were fine. three times.",
        l3=["palette:cool", "text:minimal", "subject:scene",
            "pace:slow", "cta:soft", "style:realistic"],
    ),
    SeedSpec(
        topic="The loneliness no one talks about in your 20s",
        l1=L1.EMOTIONAL, l2=L2.RESONANCE_HEALING, tier=Tier.GOOD,
        palette=["#3B5368", "#F2E8D5"],
        main_subject="an unmade bed with soft morning light",
        hook_overlay="no one texted back. you're not mad. just tired.",
        l3=["palette:cool", "text:minimal", "subject:scene",
            "pace:slow", "cta:soft", "style:realistic"],
    ),
    SeedSpec(
        topic="Missing the version of you from three years ago",
        l1=L1.EMOTIONAL, l2=L2.REGRET_STING, tier=Tier.GOOD,
        palette=["#B4B2A9", "#8B6F47"],
        main_subject="a closed journal on a windowsill at dusk",
        hook_overlay="she was louder. I keep thinking about her.",
        l3=["palette:neutral", "text:minimal", "subject:scene",
            "pace:slow", "cta:none", "style:realistic"],
    ),
    SeedSpec(
        topic="It looks like burnout but it's grief",
        l1=L1.EMOTIONAL, l2=L2.CONTRAST_TWIST, tier=Tier.VIRAL,
        palette=["#4A5568", "#D4A574"],
        main_subject="a half-drunk coffee cup going cold",
        hook_overlay="you thought it was the job. look again.",
    ),
    SeedSpec(
        topic="Quiet joy: the week nothing happened",
        l1=L1.EMOTIONAL, l2=L2.RESONANCE_HEALING, tier=Tier.GOOD,
        palette=["#E8824A", "#FFF8E7"],
        main_subject="steam rising from a mug by a sunlit window",
        hook_overlay="no one called. nothing broke. you're ok.",
    ),
]


# --- English trending_event seeds (placeholder — time-sensitive) ---

EN_TRENDING_SEEDS: list[SeedSpec] = [
    # These are illustrative templates. Real trending packs need to be
    # generated live. Kept here so the retrieval pool has L1=trending_event
    # examples to anchor on.
    SeedSpec(
        topic="Awards night · the speech everyone missed",
        l1=L1.TRENDING_EVENT, l2=L2.CONTRAST_TWIST, tier=Tier.GOOD,
        palette=["#1C1C1C", "#D4A574", "#FFFFFF"],
        main_subject="a stage mic in soft spotlight",
        hook_overlay="everyone posted the win. nobody heard what she said next.",
        l3=["palette:high_contrast", "text:medium", "subject:single_object",
            "pace:medium", "cta:soft", "style:realistic"],
    ),
    SeedSpec(
        topic="Underdog championship moment",
        l1=L1.TRENDING_EVENT, l2=L2.RESONANCE_HEALING, tier=Tier.GOOD,
        palette=["#C8323F", "#FFFFFF"],
        main_subject="worn running shoes crossing a finish line",
        hook_overlay="you were feeling it too, weren't you",
    ),
    SeedSpec(
        topic="Album drop · the track nobody's talking about",
        l1=L1.TRENDING_EVENT, l2=L2.APHORISM_LESSON, tier=Tier.GOOD,
        palette=["#2C2C2A", "#E8824A"],
        main_subject="vinyl record half-pulled from its sleeve",
        hook_overlay="track 9 is the one.",
        l3=["palette:cool", "text:minimal", "subject:single_object",
            "pace:medium", "cta:soft", "style:typographic"],
    ),
]


# --- Legacy CN festival seeds (retained as contrast pool during ramp-up) ---

LEGACY_CN_FESTIVAL_SEEDS: list[SeedSpec] = [
    SeedSpec(
        topic="中秋节 · 独在异乡的年轻人",
        l1=L1.FESTIVAL, l2=L2.RESONANCE_HEALING, tier=Tier.VIRAL,
        palette=["#F5A623", "#E8824A", "#FFF8E7"],
        main_subject="a bowl of tangyuan on a windowsill",
        hook_overlay="今年你一个人过中秋吗",
        language="zh",
    ),
    SeedSpec(
        topic="中秋节 · 家人的等待",
        l1=L1.FESTIVAL, l2=L2.REGRET_STING, tier=Tier.GOOD,
        palette=["#D4A574", "#8B6F47", "#F2E8D5"],
        main_subject="empty chair at dinner table",
        hook_overlay="妈妈多留了一副碗筷",
        language="zh",
    ),
    SeedSpec(
        topic="春节 · 回家路上",
        l1=L1.FESTIVAL, l2=L2.RESONANCE_HEALING, tier=Tier.VIRAL,
        palette=["#C8323F", "#F5A623", "#2C2C2A"],
        main_subject="train window blurred night scenery",
        hook_overlay="你还记得第一次独自回家吗",
        language="zh",
    ),
    SeedSpec(
        topic="母亲节 · 子欲养而亲不待",
        l1=L1.FESTIVAL, l2=L2.REGRET_STING, tier=Tier.VIRAL,
        palette=["#8B6F47", "#D4A574"],
        main_subject="old reading glasses on open book",
        hook_overlay="她的老花镜还在桌上",
        language="zh",
    ),
    SeedSpec(
        topic="清明 · 思念的方式",
        l1=L1.FESTIVAL, l2=L2.REGRET_STING, tier=Tier.GOOD,
        palette=["#B4B2A9", "#5F5E5A"],
        main_subject="old photograph in a frame",
        hook_overlay="他的笑还停在照片里",
        language="zh",
    ),
]


# --- Language-gated copy scaffolding ---

_EN_COPY_DIR = dict(
    tone="restrained, tender, specific",
    text_density="minimal",
    pronoun="you",
    hook_type="standalone image + short line",
    cta_example="ever had a night like this?",
    avoid=[
        "stereotypical family-reunion narrative",
        "3+ consecutive cards with emotional hype words",
    ],
    narrative_arc="object -> scene -> memory -> present -> silence",
    pacing_note="~35-40s total duration",
)

_ZH_COPY_DIR = dict(
    tone="克制、温柔、具体",
    text_density="minimal",
    pronoun="你",
    hook_type="单意象 + 短句",
    cta_example="评论区说说你的",
    avoid=["全家团圆刻板叙事", "连续情绪渲染词"],
    narrative_arc="意象 → 场景 → 回忆 → 当下 → 留白",
    pacing_note="约 35-40s 总时长",
)


def _overlay_template(i: int, topic: str, hook: str, lang: str) -> str | None:
    """Lightweight placeholder overlay per-position. Real packs overwrite these."""
    if lang == "zh":
        if i == 1:
            return hook
        if i <= 3:
            return f"{topic} 场景 {i}"
        if i <= 15:
            return f"{topic} 细节 {i}"
        if i <= 35:
            return None if i % 5 == 0 else f"{topic} 展开 {i}"
        if i <= 45:
            return f"{topic} 转折 {i}"
        return None if i % 2 == 0 else f"{topic} 收尾 {i}"
    # English
    if i == 1:
        return hook
    if i <= 3:
        return f"scene {i}"
    if i <= 15:
        return f"detail {i}"
    if i <= 35:
        return None if i % 5 == 0 else f"beat {i}"
    if i <= 45:
        return f"turn {i}"
    return None if i % 2 == 0 else f"close {i}"


def _make_synthetic_pack(spec: SeedSpec, created_at: datetime) -> CaseRecord:
    """Build a minimum-viable CaseRecord from a SeedSpec."""
    total = 50

    segments = [
        Segment(range=(1, 3), role=SegmentRole.HOOK, notes="single object, warm"),
        Segment(range=(4, 15), role=SegmentRole.SETUP, notes="scene fragments"),
        Segment(range=(16, 35), role=SegmentRole.DEVELOPMENT, notes="memory details"),
        Segment(range=(36, 45), role=SegmentRole.TURN, notes="soft turn"),
        Segment(range=(46, 50), role=SegmentRole.CLOSE, notes="quiet close"),
    ]

    copy_dir = _ZH_COPY_DIR if spec.language == "zh" else _EN_COPY_DIR

    strategy = StrategyDoc(
        version="1.0",
        topic=spec.topic,
        classification=Classification(
            l1=spec.l1, l2=spec.l2,
            l3=spec.l3,
            reasoning=f"Synthetic seed for {spec.l1.value}/{spec.l2.value}",
        ),
        referenced_cases=[],
        structure=PackStructure(total_cards=total, segments=segments),
        visual_direction=VisualDirection(
            palette=spec.palette,
            main_subject=spec.main_subject,
            composition_note="large negative space for text overlay",
            style_anchor="film photography, 35mm, natural light",
        ),
        copy_direction=CopyDirection(
            tone=copy_dir["tone"],
            text_density=copy_dir["text_density"],
            pronoun=copy_dir["pronoun"],
            hook_type=copy_dir["hook_type"],
            cta=CTA(intensity="soft", example=copy_dir["cta_example"]),
        ),
        avoid=list(copy_dir["avoid"]),
        script_hint=ScriptHint(
            narrative_arc=copy_dir["narrative_arc"],
            pacing_note=copy_dir["pacing_note"],
        ),
    )

    cards = []
    for i in range(1, total + 1):
        if i <= 3:
            seg = SegmentRole.HOOK
        elif i <= 15:
            seg = SegmentRole.SETUP
        elif i <= 35:
            seg = SegmentRole.DEVELOPMENT
        elif i <= 45:
            seg = SegmentRole.TURN
        else:
            seg = SegmentRole.CLOSE

        overlay = _overlay_template(i, spec.topic, spec.hook_overlay, spec.language)

        cards.append(CardPrompt(
            position=i,
            segment=seg,
            prompt=(
                f"{spec.main_subject}, {', '.join(spec.palette)}, film photography, "
                f"35mm, natural light, shallow depth of field, negative space for overlay"
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
        topic=spec.topic,
        topic_l1=spec.l1,
        topic_l2=spec.l2,
        topic_l3=spec.l3,
        strategy_doc=strategy,
        cards=cards,
        script=script,
        metrics=None,
        tier=spec.tier,
        is_exploration=False,
        is_synthetic=True,
        created_at=created_at,
    )


_SEED_BANK_EN: dict[str, list[SeedSpec]] = {
    "festival": EN_FESTIVAL_SEEDS,
    "emotional": EN_EMOTIONAL_SEEDS,
    "trending_event": EN_TRENDING_SEEDS,
}


@click.command()
@click.option(
    "--category",
    default="all",
    type=click.Choice(["festival", "emotional", "trending_event", "all"]),
    help="L1 category to seed. 'all' seeds festival + emotional + trending_event.",
)
@click.option("--n", default=None, type=int, help="Cap total seeds (default: no cap)")
@click.option(
    "--include-legacy-cn",
    is_flag=True,
    default=False,
    help="Also seed the retained CN festival seeds (for bilingual retrieval pool)",
)
def main(category: str, n: int | None, include_legacy_cn: bool) -> None:
    configure_logging()

    # Assemble the requested seed list
    if category == "all":
        specs: list[SeedSpec] = (
            EN_FESTIVAL_SEEDS + EN_EMOTIONAL_SEEDS + EN_TRENDING_SEEDS
        )
    else:
        specs = list(_SEED_BANK_EN.get(category, []))

    if include_legacy_cn and (category in ("festival", "all")):
        specs = specs + LEGACY_CN_FESTIVAL_SEEDS

    if n:
        specs = specs[:n]

    if not specs:
        click.echo(f"no seeds available for category={category}")
        sys.exit(1)

    base_date = datetime.utcnow() - timedelta(days=60)

    click.echo(f"seeding {len(specs)} synthetic packs (category={category}, legacy_cn={include_legacy_cn})...")
    for i, spec in enumerate(specs):
        # Stagger dates so time-decay retrieval has something to work with
        created_at = base_date + timedelta(days=i * 3)
        case = _make_synthetic_pack(spec, created_at)
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
                "language": spec.language,
                "created_at": created_at.isoformat(),
            },
        )
        click.echo(
            f"  [{i+1}/{len(specs)}] ({spec.language}) {spec.topic} "
            f"[{spec.l1.value}/{spec.l2.value}/{spec.tier.value}]"
        )

    click.echo("done.")


if __name__ == "__main__":
    main()
