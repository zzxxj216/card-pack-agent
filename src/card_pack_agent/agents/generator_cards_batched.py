"""Generator 卡贴分批生成。

原理：一次让 LLM 产 50 张容易被 max_tokens 截断。按 strategy.structure.segments
分批，每批 10-15 张，共享 system prompt 保证风格一致。
"""
from __future__ import annotations

import structlog

from ..llm import LLMRole
from ..memory.knowledge_loader import knowledge
from ..schemas import CardPrompt, StrategyDoc
from ..structured_output import CallMeta, structured_call

log = structlog.get_logger()


CARDS_SYSTEM_TEMPLATE = """You are a card-prompt generator for a TikTok card-pack system.

The product targets an English-speaking overseas audience. All free-text fields
(composition_note, text_overlay_hint.content_suggestion) must be written in
English. The image `prompt` field is already English by convention.

{global_style_guide}

---

# Category playbook

{category_playbook}

---

# Visual anti-patterns

{anti_patterns}

---

# Output rules

- Output a raw JSON array. No markdown fence, no prose before or after.
- Each item must strictly contain these fields (no extras, no omissions):

```
{{
  "position": 1,
  "segment": "hook",
  "prompt": "film photography, 35mm, ... full English image prompt",
  "negative_prompt": "text, watermark, logo, typography, ...",
  "composition_note": "English composition note",
  "text_overlay_hint": {{
    "content_suggestion": "English overlay copy that will be composited on the card",
    "position": "top-center",
    "size_tier": "hook"
  }}
}}
```

Hard constraints:
- `position` must match the requested range exactly
- `segment` only allows: hook, setup, development, turn, close
- `prompt` MUST NOT describe any text/letters/typography that should appear on
  the card; overlay text is composited in post. Write prompts in English only.
- Every `prompt` must include the `style_anchor` phrase and colors from the
  locked palette

## Sticker composition (NON-NEGOTIABLE)

Every card is a **sticker** that a TikTok viewer pastes into their own video.
It is never a scene or a photograph of an environment.

- Every `prompt` must describe ONE focal subject (or a tight subject cluster)
  centered on a plain, near-uniform, near-white background. Include at least
  one of these isolation phrases verbatim: `die-cut sticker`,
  `isolated on plain off-white background`, `product-photo isolation`,
  `subject centered on clean light backdrop`.
- The subject must have ~8-12% clear margin on all sides.
- Do NOT describe any scene, environment, interior, exterior, landscape,
  room, floor, wall, furniture, table, surface, horizon, shelf, window,
  ground, "resting on X", or "placed on Y". If the concept feels like it
  needs two objects interacting, describe them as a floating subject group
  on a plain backdrop, not connected by environment.
- Aesthetic direction from `style_anchor` (e.g. film grain, 35mm, watercolor)
  is a TEXTURE cue applied to the subject only — never scene framing.
  "Film photography, 35mm" => film-grain look on the isolated subject, NOT
  "a film photograph of a scene".
- `negative_prompt` MUST include every one of these tokens (comma-separated,
  exact text):
  `text, watermark, logo, typography, captions, lettering, scene,
  environment, landscape, interior, room, floor, wall, furniture, table,
  surface, horizon, scenery, ground shadow, background clutter`

## Overlay text hint

- `text_overlay_hint` is an object (not a string) with exactly:
  content_suggestion, position, size_tier
- `text_overlay_hint.position` allows: top-center, top-left, bottom-center, center
- `text_overlay_hint.size_tier` allows: hook, title, body, caption
- `text_overlay_hint.content_suggestion` must be English, concise
  (hook: <= 8 words; body: <= 14 words)
- If a card has no overlay text, set `text_overlay_hint` to null
"""


BATCH_USER_TEMPLATE = """# Strategy Doc

{strategy_doc_json}

# Current batch

Generate card prompts for positions {range_start} to {range_end} ({n} cards total).

These cards belong to the **{segment_role}** segment. Follow the notes for that
segment in strategy.structure.

# Visual lock (shared across all cards in the pack)

- style_anchor: `{style_anchor}`
- palette: {palette}
- main_subject family: {main_subject}

# Prior-batch style reference (last few cards, compressed; for alignment only)

{prev_batch_summary}

# Output for this batch

Strict JSON array with exactly {n} items.
"""


def generate_cards_batched(
    strategy: StrategyDoc,
    batch_size: int = 12,
) -> tuple[list[CardPrompt], CallMeta]:
    """Generate all cards by batch, per segment.

    Strategy: iterate over strategy.structure.segments. If a segment is larger
    than batch_size, further split. Each batch is a separate LLM call but
    shares the system prompt and a compact summary of prior cards.
    """
    total_cards = strategy.structure.total_cards
    segments = strategy.structure.segments
    log.info("generator.cards.batched.start",
             total=total_cards, n_segments=len(segments))

    system = CARDS_SYSTEM_TEMPLATE.format(
        global_style_guide=knowledge.global_style_guide(),
        category_playbook=knowledge.for_category(_l1_value(strategy)),
        anti_patterns=knowledge.global_anti_patterns(),
    )

    all_cards: list[CardPrompt] = []
    aggregated_meta = CallMeta(role="generator", model="")

    # Flatten segments into batches, respecting batch_size cap
    batches = _plan_batches(segments, batch_size)

    for i, batch in enumerate(batches):
        start, end, segment_role = batch
        n = end - start + 1
        prev_summary = _summarize_prior_cards(all_cards, max_items=3)

        user = BATCH_USER_TEMPLATE.format(
            strategy_doc_json=strategy.model_dump_json(),
            range_start=start,
            range_end=end,
            n=n,
            segment_role=segment_role,
            style_anchor=strategy.visual_direction.style_anchor,
            palette=", ".join(strategy.visual_direction.palette),
            main_subject=strategy.visual_direction.main_subject,
            prev_batch_summary=prev_summary or "(首批，无参考)",
        )

        log.info("generator.cards.batch",
                 batch=i + 1, total=len(batches), range=(start, end))

        cards, meta = structured_call(
            role=LLMRole.GENERATOR,
            system=system,
            user=user,
            output_model=CardPrompt,
            is_list=True,
            max_tokens=6144,  # enough for 12-15 cards comfortably
            temperature=0.6,
        )

        # Validate positions — LLM sometimes renumbers them
        cards = _repair_positions(cards, start, end)
        all_cards.extend(cards)

        # Aggregate meta
        aggregated_meta.attempts += meta.attempts
        aggregated_meta.input_tokens += meta.input_tokens
        aggregated_meta.output_tokens += meta.output_tokens
        aggregated_meta.total_tokens = (
            aggregated_meta.input_tokens + aggregated_meta.output_tokens
        )
        aggregated_meta.estimated_cost_usd += meta.estimated_cost_usd
        aggregated_meta.model = meta.model

    # Final position sanity check
    positions = [c.position for c in all_cards]
    expected = list(range(1, total_cards + 1))
    if positions != expected:
        log.warning("generator.cards.position_mismatch",
                    got=positions[:20], expected_first_20=expected[:20])
        # Renumber to enforce 1..N
        for new_pos, card in enumerate(all_cards, start=1):
            card.position = new_pos

    log.info("generator.cards.batched.done",
             n_cards=len(all_cards),
             total_cost_usd=aggregated_meta.estimated_cost_usd)
    return all_cards, aggregated_meta


def _plan_batches(
    segments,
    batch_size: int,
) -> list[tuple[int, int, str]]:
    """Flatten segments into (start, end, role) tuples, respecting batch_size."""
    batches: list[tuple[int, int, str]] = []
    for seg in segments:
        seg_start, seg_end = seg.range
        role = seg.role.value if hasattr(seg.role, "value") else str(seg.role)
        cur = seg_start
        while cur <= seg_end:
            batch_end = min(cur + batch_size - 1, seg_end)
            batches.append((cur, batch_end, role))
            cur = batch_end + 1
    return batches


def _summarize_prior_cards(cards: list[CardPrompt], max_items: int = 3) -> str:
    """Compact textual summary of last N cards' style — NOT full prompts.

    This prevents blowing the context window when prior batches already
    produced 30+ cards, while still anchoring the style.
    """
    if not cards:
        return ""
    sample = cards[-max_items:] if len(cards) > max_items else cards
    lines = []
    for c in sample:
        overlay = (
            c.text_overlay_hint.content_suggestion if c.text_overlay_hint else "(无)"
        )
        # Keep each line short
        prompt_snippet = c.prompt[:120] + ("..." if len(c.prompt) > 120 else "")
        lines.append(f"  - pos={c.position} | {prompt_snippet} | overlay={overlay}")
    return "前序卡贴摘要：\n" + "\n".join(lines)


def _repair_positions(
    cards: list[CardPrompt], expected_start: int, expected_end: int,
) -> list[CardPrompt]:
    """LLM sometimes returns positions 1..N instead of start..end. Fix."""
    expected_n = expected_end - expected_start + 1
    if len(cards) == expected_n:
        positions = [c.position for c in cards]
        if positions != list(range(expected_start, expected_end + 1)):
            log.warning("generator.cards.renumbering_batch",
                        got=positions, expected=f"{expected_start}..{expected_end}")
            for i, card in enumerate(cards):
                card.position = expected_start + i
    elif len(cards) < expected_n:
        log.warning("generator.cards.short_batch",
                    got=len(cards), expected=expected_n)
    else:
        log.warning("generator.cards.long_batch",
                    got=len(cards), expected=expected_n)
        cards = cards[:expected_n]
    return cards


def _l1_value(strategy: StrategyDoc) -> str:
    v = strategy.classification.l1
    return v.value if hasattr(v, "value") else str(v)
